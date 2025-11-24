"""Minimal Telegram bot adapter used for alerting."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class TelegramBotConfig:
    token: Optional[str] = None
    chat_id: Optional[str] = None


class TelegramBot:
    """Lightweight wrapper around the Telegram bot HTTP API."""

    def __init__(self, config: TelegramBotConfig) -> None:
        self.config = config

    def send_message(self, message: str) -> None:
        if not self.config.token or not self.config.chat_id:
            print(f"[TELEGRAM_STUB] {message}")
            return
        try:
            import requests  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            print("requests not installed; skipping Telegram send.", file=sys.stderr)
            print(f"[TELEGRAM_FALLBACK] {message}")
            return
        url = f"https://api.telegram.org/bot{self.config.token}/sendMessage"
        payload = {"chat_id": self.config.chat_id, "text": message}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as exc:  # pragma: no cover - network side effects
            print(f"[TELEGRAM_ERROR] {exc}", file=sys.stderr)
            print(f"[TELEGRAM_FALLBACK] {message}")
