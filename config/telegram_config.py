"""Telegram bot configuration."""

from pathlib import Path
from typing import Optional

# Bot credentials (fill these in after creating bot with @BotFather)
BOT_TOKEN: Optional[str] = None  # Get from @BotFather
ALLOWED_CHAT_IDS: list[int] = []  # Your Telegram user ID(s)
ADMIN_CHAT_ID: Optional[int] = None  # Primary admin user ID

# Notification settings
NOTIFICATIONS = {
    "trade_executed": True,
    "position_closed": True,
    "daily_loss_warning": True,
    "system_error": True,
    "heartbeat_failure": True,
    "session_start": True,
    "session_end": True,
}

# Paths
BOT_STATE_PATH = Path("config/bot_state.json")
RESULTS_DIR = Path("results")
LOGS_DIR = Path("logs")

# Command configuration
MAX_TRADES_DISPLAY = 20
STATUS_UPDATE_INTERVAL = 5  # seconds
