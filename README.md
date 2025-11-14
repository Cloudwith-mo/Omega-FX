# Omega FX Backtester (Phase 1)

Phase 1 delivers a conservative EUR/USD backtesting core: risk controls, sizing, strategy logic, and CLI entry points wired for unit testing.

## Quickstart: Get Example EURUSD Data

- Repository ships without market data; keep your own MT5/broker exports local.
- For a ready-made playground file, download the public EURUSD_H1.csv from `mohammad95labbaf/EURUSD_LSTM_Attention`:
  ```bash
  python scripts/download_example_data.py
  python scripts/run_backtest.py
  ```
- This open dataset is for development/testing only — not live trading decisions.
- Swap `data/eurusd_h1.csv` with your broker export anytime; no code changes needed.

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

- **Columns**: `timestamp`, `open`, `high`, `low`, `close`, `volume` (case-insensitive; the loader normalizes names).
- **Timezone**: export timestamps in UTC (preferred) or broker time so long as the spacing is consistent; values are parsed into timezone-aware datetimes.
- **Frequency**: H1 (1-hour) EUR/USD candles sorted ascending.
- **Cleanup**: delete any blank header/footer rows before saving. The loader will drop empty lines but expects real quotes/trades.
- **Export tip**: from MT5/your broker, export H1 EUR/USD candles as CSV with the above columns separated by commas.
- **Git hygiene**: real CSV files such as `data/eurusd_h1.csv` should remain local only (they are gitignored by default).

Example command once `data/eurusd_h1.csv` is present:

```bash
python scripts/run_backtest.py --data_path data/eurusd_h1.csv
```

If `--data_path` is omitted, the CLI falls back to the default defined in `config/settings.py` (`DEFAULT_DATA_PATH`).
