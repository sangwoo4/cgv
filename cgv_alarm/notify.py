"""텔레그램 봇 + 디스코드 webhook 알림. 한쪽이 실패해도 다른 쪽은 발송한다."""

import os

import requests


def send_telegram(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return None  # 미설정
    res = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=15,
    )
    res.raise_for_status()
    return True


def send_discord(text: str):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return None  # 미설정
    res = requests.post(url, json={"content": text}, timeout=15)
    res.raise_for_status()
    return True


def send_all(text: str) -> bool:
    """설정된 모든 채널로 발송. 하나라도 성공하면 True."""
    ok = False
    configured = False
    for name, fn in (("telegram", send_telegram), ("discord", send_discord)):
        try:
            result = fn(text)
            if result is None:
                print(f"[notify] {name}: 설정 없음, 건너뜀")
            else:
                configured = True
                ok = True
        except Exception as e:
            configured = True
            print(f"[notify] {name} 발송 실패: {e}")
    if not configured:
        print("[notify] 경고: 설정된 알림 채널이 하나도 없습니다")
    return ok
