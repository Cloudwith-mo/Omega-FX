from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
import yaml

DEFAULT_NOTIFICATIONS_PATH = Path("config/notifications.yaml")


def send_telegram_message(
    text: str,
    config_path: str | Path = DEFAULT_NOTIFICATIONS_PATH,
    *,
    timeout: int = 15,
) -> bool:
    """Send a Telegram message if enabled in the config."""
    path = Path(config_path)
    if not path.exists():
        print(
            f"[Notifications] Config file {path} not found; skipping Telegram send."
        )
        return False
    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    telegram = data.get("telegram") or {}
    if not telegram.get("enabled", False):
        print("[Notifications] Telegram disabled; skipping send.")
        return False
    bot_token = telegram.get("bot_token")
    chat_id = telegram.get("chat_id")
    if not bot_token or not chat_id:
        print("[Notifications] Missing bot_token or chat_id; skipping send.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        response = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        print(f"[Notifications] Telegram request failed: {exc}")
        return False

    if response.status_code != 200:
        print(
            f"[Notifications] Telegram API returned {response.status_code}: "
            f"{response.text}"
        )
        return False

    try:
        body = response.json()
    except ValueError:
        print("[Notifications] Telegram response was not JSON.")
        return False

    if not body.get("ok", False):
        print(f"[Notifications] Telegram send failed: {body}")
        return False

    return True
