# Omega FX Backtester (Phase 1)

Phase 1 delivers a conservative EUR/USD backtesting core: risk controls, sizing, strategy logic, and CLI entry points wired for unit testing.

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
python scripts/run_backtest.py --data_path data/eurusd_placeholder.csv
```

The placeholder CSV only contains headers, so the script exits with a friendly reminder to provide real hourly EUR/USD data. Replace `--data_path` with an actual dataset to run a full backtest; results will be saved in `outputs/`.
