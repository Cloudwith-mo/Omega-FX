"""Quick test script for Telegram bot setup."""

import sys
from pathlib import Path

print("=" * 70)
print("TELEGRAM BOT SETUP CHECKER")
print("=" * 70)
print()

# Check if config file exists
CONFIG_PATH = Path("config/notifications.yaml")
print(f"1. Checking for config file...")
if not CONFIG_PATH.exists():
    print(f"   ❌ NOT FOUND: {CONFIG_PATH}")
    print()
    print("   ACTION: Create the file with your bot credentials")
    print("   See: docs/TELEGRAM_BOT_SETUP.md")
    sys.exit(1)
else:
    print(f"   ✅ FOUND: {CONFIG_PATH}")

# Check if PyYAML is installed
print()
print(f"2. Checking for PyYAML...")
try:
    import yaml
    print(f"   ✅ Installed")
except ImportError:
    print(f"   ❌ NOT INSTALLED")
    print("   ACTION: pip install PyYAML")
    sys.exit(1)

# Load and validate config
print()
print(f"3. Validating config...")
try:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    
    if not config:
        print("   ❌ Config file is empty")
        sys.exit(1)
    
    telegram = config.get("telegram", {})
    
    # Check enabled
    if not telegram.get("enabled"):
        print("   ⚠️  Telegram is disabled")
        print("   ACTION: Set 'enabled: true' in config")
    else:
        print("   ✅ Telegram enabled")
    
    # Check bot_token
    print()
    print(f"4. Checking bot_token...")
    bot_token = telegram.get("bot_token")
    if not bot_token:
        print("   ❌ bot_token not set")
        print("   ACTION: Get token from @BotFather and add to config")
        sys.exit(1)
    elif "PASTE" in bot_token or "YOUR" in bot_token:
        print("   ❌ bot_token is placeholder")
        print("   ACTION: Replace with real token from @BotFather")
        sys.exit(1)
    else:
        masked_token = f"{bot_token[:10]}...{bot_token[-10:]}" if len(bot_token) > 20 else "***"
        print(f"   ✅ bot_token set ({masked_token})")
    
    # Check chat_id
    print()
    print(f"5. Checking chat_id...")
    chat_id = telegram.get("chat_id")
    if not chat_id:
        print("   ❌ chat_id not set")
        print("   ACTION: Get your ID from @userinfobot and add to config")
        sys.exit(1)
    elif isinstance(chat_id, str) and ("PASTE" in chat_id or "YOUR" in chat_id):
        print("   ❌ chat_id is placeholder")
        print("   ACTION: Replace with your real Telegram user ID")
        sys.exit(1)
    else:
        print(f"   ✅ chat_id set ({chat_id})")
    
    print()
    print("=" * 70)
    print("✅ CONFIGURATION VALID")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Test the bot:")
    print("   python scripts/run_telegram_bot.py")
    print()
    print("2. Open Telegram and message your bot")
    print("3. Send: /start")
    print()

except Exception as e:
    print(f"   ❌ Error reading config: {e}")
    sys.exit(1)
