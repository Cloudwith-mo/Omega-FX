# FTMO Live Signal Harness

This harness mirrors the FTMO deployment preset on live data without auto-trading. Use it during free trials to “shadow trade” Omega FX before wiring real execution.

## Requirements

1. Install MetaTrader5’s Python binding inside the virtualenv:

```bash
source .venv/bin/activate
pip install MetaTrader5
```

2. Run MetaTrader 5 locally (demo or free-trial terminal) and log in so the Python API can pull rates.

## Usage

```bash
source .venv/bin/activate
python scripts/run_live_signals_ftmo.py \
  --symbols EURUSD GBPUSD USDJPY \
  --m15-bars 500 \
  --h1-bars 500 \
  --account-equity 100000
```

Every invocation:

- Fetches the latest H1 + M15 candles for each symbol from MT5.
- Applies the FTMO evaluation preset (M15_WITH_H1_CTX, FULL risk scales, two-position cap).
- Emits any qualifying signals for the most recent M15 bar into `outputs/live_signals_ftmo.csv` with:

```
timestamp,symbol,direction,entry_price,stop_loss,take_profit,
risk_fraction,session,trend_regime,volatility_regime,tier,variant
```

Schedule the script every 15 minutes (cron, launchd, Windows Task Scheduler, etc.). If a bar produces multiple signals, each is appended as a new CSV row; when no signals pass the filters the script prints “No qualifying signals.”

## Manual Shadow Trading

1. Keep the FTMO trial account open in MT5.
2. Run the script each M15 bar; when a row appears in `outputs/live_signals_ftmo.csv`, mirror it manually:
   - Enter market orders in the listed direction.
   - Use the provided stop/TP and risk fraction relative to your trial account equity.
   - Respect the tier/variant for context (A-tier only, etc.).
3. Log fills and compare to the CSV after each day. You should see the same session/trend/volatility tags as the backtester.

Once the live signals match expectations across a full trial, you’re clear to move toward auto-execution.

