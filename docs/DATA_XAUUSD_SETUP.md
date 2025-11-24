# XAUUSD Data Setup

## Expected schema (Omega data files)
All symbol files under `data/` use:

- Columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`
- `timestamp`: ISO-8601 with UTC offset (e.g., `2021-11-08 22:45:00+00:00`), sorted ascending, no gaps for the timeframe
- Prices: decimal numbers; volume: tick/lot volume from MT5 export

You can inspect EURUSD samples for reference:
```bash
python - <<'PY'
import pandas as pd
for path in ["data/EURUSD_M15.csv", "data/EURUSD_H1.csv"]:
    df = pd.read_csv(path, nrows=3)
    print(path, list(df.columns))
    print(df.head())
PY
```

## Exporting XAUUSD from MT5
1) Open MT5 → History Center → XAUUSD.
2) Export CSV for each timeframe you need: **M15**, **H1**, **H4**.
3) Save the raw files locally under `mt5_exports/` (create the folder if needed):
   - `mt5_exports/XAUUSD_M15_raw.csv`
   - `mt5_exports/XAUUSD_H1_raw.csv`
   - `mt5_exports/XAUUSD_H4_raw.csv`

## Normalize to Omega format
Use the converter to produce the canonical `data/XAUUSD_<TF>.csv` files:
```bash
python scripts/convert_mt5_history_to_data.py --symbol XAUUSD --timeframe M15 --input mt5_exports/XAUUSD_M15_raw.csv --output data/XAUUSD_M15.csv
python scripts/convert_mt5_history_to_data.py --symbol XAUUSD --timeframe H1  --input mt5_exports/XAUUSD_H1_raw.csv  --output data/XAUUSD_H1.csv
python scripts/convert_mt5_history_to_data.py --symbol XAUUSD --timeframe H4  --input mt5_exports/XAUUSD_H4_raw.csv  --output data/XAUUSD_H4.csv
```

These commands:
- detect the date/time columns from the MT5 export,
- combine them into UTC timestamps,
- standardize column names to `timestamp,open,high,low,close,volume`,
- sort ascending and drop duplicates.

## Next check
After converting, run a quick readiness snapshot to confirm XAUUSD is loaded for the multi-strategy bot:
```bash
python scripts/run_strategy_readiness_check.py --bot demo_trend_mr_london
```
Look for XAUUSD lines under each strategy (trend / mean_reversion / session) with sensible trades/day, stop sizes, and hold times.
