import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def fetch_chatChannelId(streamer: str, cookies: dict) -> str:
    url = f'https://api.chzzk.naver.com/polling/v2/channels/{streamer}/live-status'
    r = requests.get(url, cookies=cookies, headers=HEADERS, timeout=10)
    r.raise_for_status()
    j = r.json()
    chatChannelId = j['content']['chatChannelId']
    assert chatChannelId is not None
    return chatChannelId

def fetch_channelName(streamer: str) -> str:
    url = f'https://api.chzzk.naver.com/service/v1/channels/{streamer}'
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()['content']['channelName']

def fetch_accessToken(chatChannelId: str, cookies: dict):
    url = f'https://comm-api.game.naver.com/nng_main/v1/chats/access-token' \
          f'?channelId={chatChannelId}&chatType=STREAMING'
    r = requests.get(url, cookies=cookies, headers=HEADERS, timeout=10)
    r.raise_for_status()
    j = r.json()['content']
    return j['accessToken'], j['extraToken']

def fetch_userIdHash(cookies: dict) -> str:
    url = 'https://comm-api.game.naver.com/nng_main/v1/user/getUserStatus'
    r = requests.get(url, cookies=cookies, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()['content']['userIdHash']
