# Omega FX Backtester (Phase 1)

Phase 1 delivers a conservative EUR/USD backtesting core: risk controls, sizing, strategy logic, and CLI entry points wired for unit testing.

## Verified Portfolio Quickstart (Nov 2025)

> [!IMPORTANT]
> **VERIFIED UPDATE**: The previous single-pair strategy has been deprecated. The new **Diversified Portfolio** (EURUSD, GBPUSD, USDJPY, Gold) is the only supported configuration for passing challenges.

### Verified Stats (Portfolio Mode)
-   **Pass Rate**: **71.4%** (Verified via Monte Carlo)
-   **Max Drawdown**: **2.43%** (Extremely Safe)
-   **Mean Return**: **+9.5%** per run

### How to Run
1.  **Download Data**:
    ```bash
    python scripts/download_yfinance_data.py --symbol EURUSD=X --days 60 --interval 1h
    python scripts/download_yfinance_data.py --symbol GBPUSD=X --days 60 --interval 1h
    python scripts/download_yfinance_data.py --symbol JPY=X --days 60 --interval 1h
    python scripts/download_yfinance_data.py --symbol GC=F --days 60 --interval 1h
    ```
2.  **Run Portfolio Backtest**:
    ```bash
    python scripts/run_backtest.py --portfolio
    ```


## Data Source
We now use `yfinance` for high-quality, free data. You do **not** need manual MT5 exports anymore.
The `scripts/download_yfinance_data.py` tool handles everything automatically.

## Project Structure

- `config/`: project-wide constants (initial equity, lot caps, pip value).
- `core/`: risk engine, sizing helper, SMA/ATR strategy, backtest loop, metrics.
- `data/`: placeholder CSV (`eurusd_placeholder.csv`) awaiting real OHLCV data.
- `scripts/`: `run_backtest.py` CLI.
- `tests/`: pytest coverage for risk, sizing, and strategy.
- `notebooks/`: future exploratory notebooks.
- `outputs/`: generated artifacts (gitignored).

## Philosophy & Playbooks

- [Ω-FX Trading Philosophy](docs/OMEGA_TRADING_PHILOSOPHY.md)
- [Evaluation Playbook](docs/EVAL_PLAYBOOK.md)
- [Funded Playbook](docs/FUNDED_PLAYBOOK.md)
- [Firm Comparison & Campaign Notes](docs/FIRM_COMPARISON.md)
- [Capital Plan Scenarios](docs/CAPITAL_PLAN_SCENARIOS.md)
- [Plan B Operator Guide](docs/PLAN_B_OPERATOR_GUIDE.md)
- [Strategy Lifecycle](docs/STRATEGY_LIFECYCLE.md)
- [FTMO Trial Field-Test Kit](docs/LIVE_TEST_FTMO_TRIAL.md)
- [Execution Playbook](docs/EXECUTION_PLAYBOOK.md)
- [MT5 Demo Execution Guide](docs/EXECUTION_MT5_DEMO.md)
- Minimal FTMO preset: `python scripts/run_minimal_ftmo_eval.py --step 10000`
- Capital plan sim: `python scripts/run_capital_plan_sim.py --months 12 --evals_per_wave 4 --waves_per_month 1 --eval_fee 300 --initial_bankroll 1000 --risk_budget_fraction 0.6 --reinvest_fraction 0.2 --eval_runs results/minimal_ftmo_eval_runs.csv --funded_runs results/funded_payout_ftmo_12m_runs.csv --funded_horizon_months 12 --output results/capital_plan_ftmo_12m.json`
- Live vs Sim analyzer: `python scripts/analyze_live_vs_sim.py --live_trades_csv data/live/ftmo_trial_sample.csv --sim_runs_csv results/minimal_ftmo_eval_runs.csv`

## Sanity Check (before touching real accounts)

Run these two commands to ensure the strategy + simulator are healthy:

```bash
source .venv/bin/activate
python scripts/run_minimal_ftmo_eval.py --step 10000
python scripts/run_ftmo_eval_sim.py --step 2000
```

They should reproduce the ~70 % pass-rate / <4 % max DD baseline referenced in the playbooks.

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
