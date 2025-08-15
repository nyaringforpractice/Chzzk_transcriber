import os, time, json, subprocess, shlex, math
from pathlib import Path
from datetime import datetime, timedelta
import difflib

try:
    from distutils.util import strtobool
except ImportError:
    def strtobool(v): return str(v).lower() in ("y","yes","t","true","1")

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

DATA = Path("/data")
CH_A = DATA/"chunks/a"
CH_B = DATA/"chunks/b"
OUTD = DATA/"transcripts"
OUTD.mkdir(parents=True, exist_ok=True)

ENV = os.environ
VAD_ENABLE = strtobool(ENV.get("VAD_ENABLE","false"))
VAD_MODE   = int(ENV.get("VAD_MODE","2"))
LANG       = ENV.get("STT_LANG","auto")
MODEL      = ENV.get("WHISPER_MODEL","ggml-small-q5_0.bin")
MODEL_URL  = ENV.get("WHISPER_MODEL_URL","")
RETAIN_HRS = int(ENV.get("RETAIN_HOURS","24"))
DISK_MAX_GB= float(ENV.get("DISK_MAX_GB","10"))
CHUNK_SEC  = int(ENV.get("CHUNK_SECONDS","5"))
OVERLAP_EN = strtobool(ENV.get("OVERLAP_ENABLE","false"))

MODELS_DIR = Path("/models")
MODEL_PATH = MODELS_DIR/MODEL
MODELS_DIR.mkdir(exist_ok=True, parents=True)

def ensure_model():
    if MODEL_PATH.exists(): return
    if not MODEL_URL:
        raise SystemExit("WHISPER_MODEL_URL not set and model not found.")
    print(f"[stt] downloading model {MODEL} ...")
    subprocess.run(["curl","-L",MODEL_URL,"-o",str(MODEL_PATH)], check=True)

def wav_is_complete(p: Path)->bool:
    if not p.exists(): return False
    s1 = p.stat().st_size
    time.sleep(0.15)
    s2 = p.stat().st_size
    return s1 == s2 and s2 > 44  # WAV 최소 헤더

def has_voice_webrtc(p: Path)->bool:
    if not VAD_ENABLE or webrtcvad is None:
        return True
    import wave, contextlib
    with contextlib.closing(wave.open(str(p),'rb')) as wf:
        if wf.getframerate()!=16000 or wf.getnchannels()!=1 or wf.getsampwidth()!=2:
            return True
        vad = webrtcvad.Vad(VAD_MODE)
        frame_ms = 30
        n_bytes = int(16000 * (frame_ms/1000.0)) * 2
        while True:
            data = wf.readframes(int(16000 * (frame_ms/1000.0)))
            if len(data) < n_bytes:
                break
            if vad.is_speech(data, 16000):
                return True
    return False

def transcribe(p: Path)->str:
    out_prefix = OUTD / p.stem
    cmd = f'/usr/local/bin/whisper_main -m "{MODEL_PATH}" -l {LANG} -f "{p}" -otxt -of "{out_prefix}"'
    subprocess.run(shlex.split(cmd), check=True)
    txt_file = OUTD / f"{p.stem}.txt"
    if txt_file.exists():
        return txt_file.read_text(encoding="utf-8", errors="ignore").strip()
    return ""

def similarity(a,b)->float:
    if not a or not b: return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()

def merge_line(buf:list, line:str):
    line = (line or "").strip()
    if not line: return
    if buf and similarity(buf[-1], line) >= 0.90:
        return
    buf.append(line)

def pick_better(a_txt:str, b_txt:str)->str:
    if not a_txt: return b_txt
    if not b_txt: return a_txt
    if similarity(a_txt, b_txt) >= 0.85:
        return a_txt if len(a_txt)>=len(b_txt) else b_txt
    # 유사하지 않으면 길이순으로 정렬해 이어붙이고, 중복 억제는 merge_line에서 처리
    if len(a_txt) >= len(b_txt):
        return f"{a_txt} {b_txt}".strip()
    else:
        return f"{b_txt} {a_txt}".strip()

def janitor():
    # 시간 기반 제거
    cutoff = datetime.utcnow() - timedelta(hours=RETAIN_HRS)
    def purge_old(dir: Path, pattern: str):
        for p in dir.glob(pattern):
            stem = p.stem
            try:
                t = datetime.strptime(stem, "%Y%m%d-%H%M%S")
                if t < cutoff:
                    p.unlink(missing_ok=True)
            except:
                # 타임스탬프가 아니면 mtime으로 판단
                if datetime.utcfromtimestamp(p.stat().st_mtime) < cutoff:
                    p.unlink(missing_ok=True)
    for d in [CH_A, CH_B, OUTD]:
        purge_old(d, "*.wav")
        purge_old(d, "*.txt")
        purge_old(d, "*.json")

    # 용량 제한
    def du_bytes(path: Path)->int:
        total = 0
        for root,_,files in os.walk(path):
            for f in files:
                total += (Path(root)/f).stat().st_size
        return total
    limit = int(DISK_MAX_GB * 1024**3)
    while du_bytes(DATA) > limit:
        # 가장 오래된 파일부터 제거
        candidates = []
        for base in [CH_A, CH_B, OUTD]:
            for p in base.glob("*.*"):
                try:
                    t = datetime.strptime(p.stem, "%Y%m%d-%H%M%S")
                except:
                    t = datetime.utcfromtimestamp(p.stat().st_mtime)
                candidates.append((t, p))
        if not candidates: break
        candidates.sort(key=lambda x: x[0])
        oldest = candidates[0][1]
        oldest.unlink(missing_ok=True)

def main():
    print("[stt] starting...")
    ensure_model()
    processed = set()
    OUTD.mkdir(exist_ok=True)
    (OUTD/"live.txt").touch(exist_ok=True)
    buffer = []

    while True:
        files = [p for p in CH_A.glob("*.wav") if wav_is_complete(p)]
        if OVERLAP_EN:
            files += [p for p in CH_B.glob("*.wav") if wav_is_complete(p)]
        # 타임스탬프 정렬
        files = sorted(set(files), key=lambda p: p.stem)

        for p in files:
            if p in processed: continue
            if not has_voice_webrtc(p):
                processed.add(p); continue

            ts = p.stem
            a = CH_A/f"{ts}.wav"
            b = CH_B/f"{ts}.wav"
            if OVERLAP_EN and a.exists() and b.exists():
                a_txt = transcribe(a)
                b_txt = transcribe(b)
                merged = pick_better(a_txt, b_txt)
                merge_line(buffer, merged)
                processed.update({a,b})
            else:
                txt = transcribe(p)
                merge_line(buffer, txt)
                processed.add(p)

            if buffer:
                with open(OUTD/"live.txt","a",encoding="utf-8") as f:
                    for line in buffer:
                        f.write(line+"\n")
                buffer.clear()

        janitor()
        time.sleep(0.2)

if __name__ == "__main__":
    main()
