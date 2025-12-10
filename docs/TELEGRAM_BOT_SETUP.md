# Omega FX Phase 6: Telegram Bot Setup Guide

This guide will help you set up the Telegram bot for remote monitoring and control.

## Prerequisites

- Telegram account (mobile app or desktop)
- Python 3.10+
- Omega FX bot running

## Step 1: Install Dependencies

```bash
pip install python-telegram-bot pyyaml requests
```

## Step 2: Create Your Telegram Bot

1. **Open Telegram** and search for `@BotFather`
2. **Start a chat** with BotFather
3. **Create a new bot**:
   ```
   /newbot
   ```
4. **Choose a name** (e.g., "Omega FX Monitor")
5. **Choose a username** (e.g., "omegafx_monitor_bot")
6. **Save the bot token** you receive (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

## Step 3: Get Your Chat ID

1. **Search for `@userinfobot`** on Telegram
2. **Start a chat** with it
3. **Copy your user ID** (a number like `123456789`)

## Step 4: Configure the Bot

Create or update `config/notifications.yaml`:

```yaml
telegram:
  enabled: true
  bot_token: "YOUR_BOT_TOKEN_FROM_STEP_2"
  chat_id: YOUR_USER_ID_FROM_STEP_3
```

**Example**:
```yaml
telegram:
  enabled: true
  bot_token: "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456"
  chatid: 987654321
```

## Step 5: Start the Bot

```bash
# From Omega-FX directory
python scripts/run_telegram_bot.py
```

You should see:
```
INFO - Starting Omega FX Telegram Bot
INFO - Bot is running. Press Ctrl+C to stop.
```

## Step 6: Test the Bot

1. **Open Telegram** and search for your bot username
2. **Start a chat** with your bot
3. **Send `/start`** - you should get a welcome message
4. **Try `/status`** - see your current trading status
5. **Try `/help`** - see all available commands

## Available Commands

### Monitoring
- `/status` - Current equity, P&L, open positions
- `/trades [N]` - Last N trades (default 10)
- `/open` - Details of open positions
- `/health` - System health check

### Control
- `/pause` - Pause new trade signals
- `/resume` - Resume trading
- `/flatten` - Close all positions (EMERGENCY - not yet implemented)

### Info
- `/help` - Show command list

## Step 7: Enable Heartbeat Monitoring (Optional)

The heartbeat monitor pings an external service to detect if your bot crashes.

### Option A: Use Healthchecks.io (Free)

1. Go to https://healthchecks.io
2. Sign up (free tier is fine)
3. Create a new check
4. Copy the ping URL
5. Create `config/healthcheck.yaml`:

```yaml
healthcheck_url: "https://hc-ping.com/YOUR-UUID-HERE"
interval_seconds: 300  # 5 minutes
```

6. Update autopilot to enable heartbeat (see Step 8)

### Option B: Skip for Now

Heartbeat monitoring is optional. You can skip this and still use the bot.

## Step 8: Integrate with Autopilot

Update your autopilot script to send heartbeats:

```python
from monitoring.heartbeat import create_heartbeat_monitor

# In your autopilot main loop
heartbeat = create_heartbeat_monitor()

while running:
    # ... your trading logic ...
    
    # Send heartbeat every iteration
    heartbeat.beat(metadata={
        "session_id": session_id,
        "equity": current_equity,
        "trades_today": trades_today,
    })
    
    time.sleep(60)
```

## Running on VPS

### Start Bot in Background

```bash
# Using screen
screen -S telegram_bot
python scripts/run_telegram_bot.py
# Press Ctrl+A then D to detach

# Check it's running
screen -ls

# Reattach later
screen -r telegram_bot
```

### Auto-Start on VPS Reboot

Add to crontab:
```bash
crontab -e
```

Add line:
```
@reboot cd /path/to/Omega-FX && /path/to/python scripts/run_telegram_bot.py > logs/telegram_bot.log 2>&1
```

## Troubleshooting

### "Unauthorized" Message
- Double-check your `chat_id` in config
- Make sure you're messaging the correct bot

### Bot Not Responding
- Check bot is running: `ps aux | grep run_telegram_bot`
- Check logs for errors
- Verify bot token is correct

### `/status` Shows No Data
- Ensure autopilot has run and created result files
- Check `results/mt5_demo_exec_live_summary.json` exists
- Verify file paths in bot code

### Healthcheck Failing
- Test ping URL manually: `curl https://hc-ping.com/YOUR-UUID`
- Check internet connection from VPS
- Verify healthcheck  URL in config

## Security Notes

- **Never share** your bot token
- **Never commit** `config/notifications.yaml` to git
- Only share your bot username with trusted people
- Use `/pause` immediately if you suspect compromise

## Next Steps

1. [ ] Set up bot and test all commands
2. [ ] Configure healthcheck monitoring
3. [ ] Test Emergency `/pause` and `/resume`
4. [ ] Run demo for 1 week with bot monitoring
5. [ ] Deploy to VPS with auto-start
6. [ ] Buy evaluations once bot is stable

---

## Quick Reference

```bash
# Start bot
python scripts/run_telegram_bot.py

# Check bot is running
ps aux | grep run_telegram_bot

# Kill bot
pkill -f run_telegram_bot

# View logs
tail -f logs/telegram_bot.log
```

## Support

If you encounter issues:
1. Check logs
2. Verify configuration files
3. Test bot token with @BotFather
4. Re-read this guide

Good luck! 🚀
