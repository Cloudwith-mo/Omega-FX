# Omega FX Backtester (Phase 1)

Phase 1 delivers a conservative EUR/USD backtesting core: risk controls, sizing, strategy logic, and CLI entry points wired for unit testing.

## Quickstart: Example EURUSD Data (demo only)

- Repository ships without market data; keep your own MT5/broker exports local.
- For a playground EURUSD file only (not for live trading), you may run:
  ```bash
  python scripts/download_example_data.py
  python scripts/run_backtest.py
  ```
- This open dataset is purely for development smoke tests. The real workflow below expects MT5 exports for **all** symbols.

## MT5 Data Export → Omega FX

1. In MT5, open each symbol (EURUSD, GBPUSD, USDJPY) on the H1 timeframe and export as CSV (File → Save As…). Save to `raw_data/<SYMBOL>_H1_raw.csv`.
2. Normalize each export:
   ```bash
   python scripts/prepare_mt5_data.py --symbol EURUSD --input raw_data/EURUSD_H1_raw.csv --output data/EURUSD_H1.csv
   python scripts/prepare_mt5_data.py --symbol GBPUSD --input raw_data/GBPUSD_H1_raw.csv --output data/GBPUSD_H1.csv
   python scripts/prepare_mt5_data.py --symbol USDJPY --input raw_data/USDJPY_H1_raw.csv --output data/USDJPY_H1.csv
   ```
   - The script handles standard MT5 columns (`<DATE>`, `<TIME>`, `<OPEN>`, …, `<TICKVOL>`), merges date+time, sorts ascending, and validates the H1 spacing.
   - Timestamps are parsed as UTC. If your broker export is local time, either adjust prior to running or note the offset when interpreting results.
3. Run the full portfolio backtest & challenge sim (will auto-skip symbols without data, but aim to provide all three):
   ```bash
   python scripts/run_backtest.py --portfolio
   python scripts/run_challenge_sim.py --portfolio --step 2000
   ```
   The risk engine enforces one global position at a time plus FundedNext rules (2 % daily, 4 % trailing, 3 % / 6 % prop caps) across all loaded symbols.

## Project Structure

- `config/`: project-wide constants (initial equity, lot caps, pip value).
- `core/`: risk engine, sizing helper, SMA/ATR strategy, backtest loop, metrics.
- `data/`: placeholder CSV (`eurusd_placeholder.csv`) awaiting real OHLCV data.
- `scripts/`: `run_backtest.py` CLI.
- `tests/`: pytest coverage for risk, sizing, and strategy.
- `notebooks/`: future exploratory notebooks.
- `outputs/`: generated artifacts (gitignored).

## Requirements

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running Tests

```bash
pytest
```

## Running the Backtest

```bash
python scripts/run_backtest.py --data_path data/eurusd_h1.csv
```

If you point to the header-only placeholder, the CLI will stop early and remind you to supply real data. With a valid CSV, equity curves and trade logs will be saved in `outputs/`.

## Data Requirements

- **Columns**: `timestamp`, `open`, `high`, `low`, `close`, `volume` (case-insensitive; the loader normalizes names). The MT5 prep script emits this schema automatically.
- **Timezone**: export timestamps in UTC when possible. If the raw MT5 file is in broker time, document the offset; the loader ingests the values as-is but treats them as UTC.
- **Frequency**: H1 (1-hour) candles, sorted ascending, one file per symbol (EURUSD/GBPUSD/USDJPY).
- **Cleanup**: delete any blank header/footer rows before saving. The prep script drops malformed rows but expects real quotes/trades.
- **Git hygiene**: real CSV files such as `data/EURUSD_H1.csv` must remain local only (gitignored by default).

Legacy single-symbol runs still work (e.g. `python scripts/run_backtest.py --data_path data/eurusd_h1.csv`), but the recommended flow is `--portfolio` after preparing all MT5 exports.
