#!/usr/bin/env python3
"""Telegram bot for Omega FX remote monitoring and control.

Setup Instructions:
1. Message @BotFather on Telegram
2. Create new bot with /newbot
3. Save your bot token
4. Get your chat ID by messaging @userinfobot
5. Update config/notifications.yaml with bot_token and chat_id
6. Run this script: python scripts/run_telegram_bot.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add repo to path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
except ImportError:
    print("ERROR: python-telegram-bot not installed")
    print("Install with: pip install python-telegram-bot")
    sys.exit(1)

import yaml

from core.monitoring_helpers import (
    DEFAULT_LOG_PATH,
    DEFAULT_SUMMARY_PATH,
    build_status_payload,
)

logger = logging.getLogger(__name__)

# Config paths
CONFIG_PATH = Path("config/notifications.yaml")
STATE_PATH = Path("config/bot_state.json")


class OmegaBot:
    """Telegram bot for Omega FX."""

    def __init__(self, bot_token: str, allowed_chat_ids: list[int]):
        """Initialize bot."""
        self.bot_token = bot_token
        self.allowed_chat_ids = set(allowed_chat_ids)
        self.application = Application.builder().token(bot_token).build()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Register command handlers."""
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("trades", self.cmd_trades))
        self.application.add_handler(CommandHandler("open", self.cmd_open))
        self.application.add_handler(CommandHandler("pause", self.cmd_pause))
        self.application.add_handler(CommandHandler("resume", self.cmd_resume))
        self.application.add_handler(CommandHandler("flatten", self.cmd_flatten))
        self.application.add_handler(CommandHandler("health", self.cmd_health))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

    def _check_auth(self, update: Update) -> bool:
        """Check if user is authorized."""
        if not update.effective_user:
            return False
        user_id = update.effective_user.id
        if user_id not in self.allowed_chat_ids:
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            return False
        return True

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self._check_auth(update):
            await update.message.reply_text("❌ Unauthorized")
            return

        await update.message.reply_text(
            "🤖 *Omega FX Bot*\n\n"
            "I monitor your trading bot and alert you to important events.\n\n"
            "Use /help to see available commands.",
            parse_mode="Markdown",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not self._check_auth(update):
            return

        help_text = """
🤖 *Omega FX Bot Commands*

*Monitoring*
/status - Current equity, P&L, positions
/trades [N] - Last N trades (default 10)
/open - Open positions detail
/health - System health check

*Control*
/pause - Pause new trade signals
/resume - Resume trading
/flatten - Close all positions (EMERGENCY)

*Info*
/help - Show this message
        """
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if not self._check_auth(update):
            return

        try:
            status = build_status_payload(
                hours=24.0,
                log_path=DEFAULT_LOG_PATH,
                summary_path=DEFAULT_SUMMARY_PATH,
                include_historical=False,
            )

            session_id = status.get("session_id", "unknown")
            env = status.get("env", "unknown").upper()
            tier = status.get("tier", "unknown").title()

            start_equity = status.get("session_start_equity", 0)
            end_equity = status.get("session_end_equity", 0)
            session_pnl = status.get("session_pnl", 0)
            session_pnl_pct = (session_pnl / start_equity * 100) if start_equity else 0

            open_positions = status.get("open_positions", {})
            open_count = open_positions.get("count", 0)
            open_pnl = open_positions.get("total_pnl", 0)

            last_24h_pnl = status.get("last_24h_pnl", 0)
            last_24h_trades = status.get("last_24h_trades", 0)
            last_24h_wr = status.get("last_24h_win_rate", 0) * 100

            message = f"""
📊 *Status Report*

*Session*
• ID: `{session_id}`
• Env: {env}
• Risk: {tier}

*Equity*
• Start: ${start_equity:,.2f}
• Current: ${end_equity:,.2f}
• Session P&L: ${session_pnl:+,.2f} ({session_pnl_pct:+.2f}%)

*Open Positions*
• Count: {open_count}
• Floating P&L: ${open_pnl:+,.2f}

*Last 24h*
• Trades: {last_24h_trades}
• P&L: ${last_24h_pnl:+,.2f}
• Win Rate: {last_24h_wr:.1f}%

_Updated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC_
            """
            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in /status: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /trades command."""
        if not self._check_auth(update):
            return

        # Parse count argument
        count = 10
        if context.args and context.args[0].isdigit():
            count = min(int(context.args[0]), 50)

        try:
            from scripts.query_last_trades import load_trades

            trades = load_trades(
                DEFAULT_LOG_PATH,
                hours=168.0,  # Last week
                limit=count,
            )

            if not trades:
                await update.message.reply_text("No trades found")
                return

            lines = [f"📜 *Last {len(trades)} Trades*\n"]
            for trade in trades[-count:]:
                symbol = trade.get("symbol", "?")
                direction = trade.get("direction", "?")
                pnl = trade.get("pnl", 0)
                timestamp = trade.get("close_timestamp", trade.get("timestamp", "?"))
                icon = "✅" if pnl > 0 else "❌"
                lines.append(f"{icon} {symbol} {direction} ${pnl:+.2f}")

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in /trades: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def cmd_open(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /open command."""
        if not self._check_auth(update):
            return

        try:
            status = build_status_payload(
                hours=24.0,
                log_path=DEFAULT_LOG_PATH,
                summary_path=DEFAULT_SUMMARY_PATH,
            )

            open_positions = status.get("open_positions", {})
            positions = open_positions.get("positions", [])

            if not positions:
                await update.message.reply_text("No open positions")
                return

            lines = [f"📍 *Open Positions ({len(positions)})*\n"]
            for pos in positions:
                symbol = pos.get("symbol", "?")
                direction = pos.get("direction", "?")
                entry = pos.get("entry_price", 0)
                current = pos.get("current_price", 0)
                pnl = pos.get("pnl", 0)
                lines.append(
                    f"{symbol} {direction}\n"
                    f"  Entry: {entry:.5f} → {current:.5f}\n"
                    f"  P&L: ${pnl:+.2f}"
                )

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in /open: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /pause command."""
        if not self._check_auth(update):
            return

        try:
            state = self._load_state()
            state["trading_enabled"] = False
            state["last_updated"] = datetime.utcnow().isoformat()
            self._save_state(state)

            await update.message.reply_text(
                "⏸️ *Trading Paused*\n\n"
                "No new signals will be executed.\n"
                "Open positions remain active.\n\n"
                "Use /resume to re-enable trading.",
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Error in /pause: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resume command."""
        if not self._check_auth(update):
            return

        try:
            state = self._load_state()
            state["trading_enabled"] = True
            state["last_updated"] = datetime.utcnow().isoformat()
            self._save_state(state)

            await update.message.reply_text(
                "▶️ *Trading Resumed*\n\n" "New signals will be executed normally.",
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Error in /resume: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def cmd_flatten(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /flatten command."""
        if not self._check_auth(update):
            return

        await update.message.reply_text(
            "🚨 *FLATTEN NOT IMPLEMENTED*\n\n"
            "This command requires MT5 integration.\n"
            "To manually close positions:\n"
            "1. SSH into VPS\n"
            "2. Open MT5\n"
            "3. Close positions manually\n\n"
            "⚠️ This is a critical feature to implement before live trading!",
            parse_mode="Markdown",
        )

    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /health command."""
        if not self._check_auth(update):
            return

        try:
            state = self._load_state()
            trading_enabled = state.get("trading_enabled", True)
            last_heartbeat = state.get("last_heartbeat")

            # Check if files exist
            summary_exists = DEFAULT_SUMMARY_PATH.exists()
            log_exists = DEFAULT_LOG_PATH.exists()

            # Check heartbeat freshness
            heartbeat_status = "❓ Unknown"
            if last_heartbeat:
                last_beat = datetime.fromisoformat(last_heartbeat)
                age = (datetime.utcnow() - last_beat).total_seconds()
                if age < 600:  # 10 minutes
                    heartbeat_status = f"✅ {age:.0f}s ago"
                else:
                    heartbeat_status = f"⚠️ {age/60:.1f}m ago (STALE)"

            message = f"""
🏥 *Health Check*

*System*
• Summary File: {'✅' if summary_exists else '❌'}
• Log File: {'✅' if log_exists else '❌'}
• Trading: {'▶️ Enabled' if trading_enabled else '⏸️ Paused'}

*Monitoring*
• Heartbeat: {heartbeat_status}

_Checked: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC_
            """
            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in /health: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    def _load_state(self) -> dict:
        """Load bot state."""
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text())
        return {"trading_enabled": True}

    def _save_state(self, state: dict) -> None:
        """Save bot state."""
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2))

    async def run(self) -> None:
        """Run the bot."""
        logger.info("Starting Omega FX Telegram Bot")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("Bot is running. Press Ctrl+C to stop.")
        # Keep running until interrupted
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down bot")
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()


def load_config() -> tuple[str, list[int]]:
    """Load bot configuration."""
    if not CONFIG_PATH.exists():
        print(f"ERROR: Config file not found: {CONFIG_PATH}")
        print("\nCreate config/notifications.yaml with:")
        print("""
telegram:
  enabled: true
  bot_token: "YOUR_BOT_TOKEN_FROM_BOTFATHER"
  chat_id: YOUR_TELEGRAM_USER_ID
        """)
        sys.exit(1)

    config = yaml.safe_load(CONFIG_PATH.read_text())
    telegram = config.get("telegram", {})

    if not telegram.get("enabled"):
        print("ERROR: Telegram is disabled in config")
        sys.exit(1)

    bot_token = telegram.get("bot_token")
    chat_id = telegram.get("chat_id")

    if not bot_token or not chat_id:
        print("ERROR: Missing bot_token or chat_id in config")
        sys.exit(1)

    return bot_token, [int(chat_id)]


async def main() -> None:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    bot_token, allowed_chat_ids = load_config()
    bot = OmegaBot(bot_token, allowed_chat_ids)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
