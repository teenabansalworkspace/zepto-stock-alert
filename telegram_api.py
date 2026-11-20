"""Very small wrapper around the free Telegram Bot API."""
import html
import time

import requests

import config

API = "https://api.telegram.org/bot{token}/{method}"


def call(method: str, **params):
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN set nahi hai (.env file ya GitHub Secret mein daalein)")
    for attempt in range(3):
        try:
            r = requests.post(API.format(token=config.BOT_TOKEN, method=method), json=params, timeout=30)
            data = r.json()
        except Exception as exc:  # network hiccup
            print(f"[telegram] {method} error: {exc}")
            time.sleep(2 + attempt * 3)
            continue
        if data.get("ok"):
            return data.get("result")
        if data.get("error_code") == 429:  # rate limited
            time.sleep(int(data.get("parameters", {}).get("retry_after", 5)) + 1)
            continue
        print(f"[telegram] {method} failed: {data.get('description')}")
        return None
    return None


def send(chat_id, text: str) -> bool:
    return call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                disable_web_page_preview=False) is not None


def get_updates(offset: int):
    return call("getUpdates", offset=offset, timeout=0,
                allowed_updates=["message", "my_chat_member"]) or []


def esc(text) -> str:
    return html.escape(str(text), quote=False)
