import os, json, time, logging, datetime
from pathlib import Path
from websocket import WebSocket
from chzzk_chat_type import CHZZK_CHAT_CMD
import chzzk_api as api

ENV = os.environ
STREAMER = ENV.get('CHANNEL_ID', '').strip()
NID_AUT  = ENV.get('NID_AUT', '').strip()
NID_SES  = ENV.get('NID_SES', '').strip()
RECENT   = int(ENV.get('CHZZKCHAT_RECENT_COUNT', '50'))
LOG_FILE = ENV.get('CHZZKCHAT_LOG_FILE', '/data/chat/chat.log')
ENABLE   = ENV.get('CHZZKCHAT_ENABLE', 'true').lower() in ('1','true','y','yes')

def main():
    if not ENABLE:
        print("[chzzkchat] disabled by env, exiting.")
        return
    if not (STREAMER and NID_AUT and NID_SES):
        raise SystemExit("[chzzkchat] CHANNEL_ID / NID_AUT / NID_SES is required")

    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8'),
                  logging.StreamHandler()],
        format='%(message)s'
    )

    cookies = {'NID_AUT': NID_AUT, 'NID_SES': NID_SES}
    channelName   = api.fetch_channelName(STREAMER)
    userIdHash    = api.fetch_userIdHash(cookies)

    print(f"[chzzkchat] target: {channelName} ({STREAMER})")
    sock = None
    sid  = None

    def connect():
        nonlocal sock, sid
        chatChannelId = api.fetch_chatChannelId(STREAMER, cookies)
        accessToken, extraToken = api.fetch_accessToken(chatChannelId, cookies)

        sock = WebSocket()
        sock.connect('wss://kr-ss1.chat.naver.com/chat')
        default = {"ver": "2", "svcid": "game", "cid": chatChannelId}

        # 1) connect
        send = {
            "cmd": CHZZK_CHAT_CMD['connect'], "tid": 1,
            "bdy": {"uid": userIdHash, "devType": 2001, "accTkn": accessToken, "auth": "SEND"}
        }
        sock.send(json.dumps({**default, **send}))
        resp = json.loads(sock.recv())
        sid  = resp['bdy']['sid']
        print("[chzzkchat] connected, sid:", sid)

        # 2) recent chat
        send = {"cmd": CHZZK_CHAT_CMD['request_recent_chat'], "tid": 2, "sid": sid,
                "bdy": {"recentMessageCount": RECENT}}
        sock.send(json.dumps({**default, **send}))
        sock.recv()  # ignore payload

        return default, extraToken

    default, extraToken = connect()

    while True:
        try:
            raw = sock.recv()
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(1.0)
            default, extraToken = connect()
            continue

        try:
            msg = json.loads(raw)
        except Exception:
            continue

        cmd = msg.get('cmd')
        if cmd == CHZZK_CHAT_CMD['ping']:
            sock.send(json.dumps({"ver":"2","cmd":CHZZK_CHAT_CMD['pong']}))
            # 방송 중 chatChannelId 변경 대응
            try:
                new_cid = api.fetch_chatChannelId(STREAMER, cookies)
                if new_cid != default['cid']:
                    default, extraToken = connect()
            except Exception:
                pass
            continue

        if cmd not in (CHZZK_CHAT_CMD['chat'], CHZZK_CHAT_CMD['donation']):
            continue

        chat_type = '채팅' if cmd == CHZZK_CHAT_CMD['chat'] else '후원'
        for b in msg.get('bdy', []):
            # 익명 후원
            if b.get('uid') == 'anonymous':
                nickname = '익명의 후원자'
            else:
                try:
                    profile = json.loads(b.get('profile','{}'))
                    nickname = profile.get('nickname','?')
                except Exception:
                    nickname = '?'

            if 'msg' not in b:  # 메세지 없는 시스템 이벤트
                continue

            ts = datetime.datetime.fromtimestamp(b['msgTime']/1000)
            ts_s = datetime.datetime.strftime(ts, '%Y-%m-%d %H:%M:%S')
            logging.info(f'[{ts_s}][{chat_type}] {nickname} : {b["msg"]}')
