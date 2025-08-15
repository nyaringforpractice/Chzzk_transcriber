# ---------- build whisper.cpp ----------
FROM debian:bookworm-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/ggml-org/whisper.cpp /src/whisper.cpp
WORKDIR /src/whisper.cpp
RUN make -j

# ---------- runtime ----------
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg python3 python3-pip ca-certificates curl tzdata \
    && rm -rf /var/lib/apt/lists/*
# streamlink + STT 보조 + ChzzkChat 의존성
RUN pip3 install --no-cache-dir streamlink webrtcvad requests websocket-client

# whisper.cpp 실행파일
COPY --from=builder /src/whisper.cpp/main /usr/local/bin/whisper_main

WORKDIR /app
COPY entrypoint_recorder.sh /app/entrypoint_recorder.sh
COPY stt_worker.py          /app/stt_worker.py
COPY chzzk_api.py           /app/chzzk_api.py
COPY chzzk_chat_type.py     /app/chzzk_chat_type.py
COPY chzzkchat_service.py   /app/chzzkchat_service.py
RUN chmod +x /app/entrypoint_recorder.sh