# Monitoring Workflow

## Daily Ops
- **Start the bot:** `python scripts/run_autopilot.py --bot demo_trend_mr_london` (canonical). Outputs `results/autopilot_demo_trend_mr_london_signals.csv` plus alert stubs.
- **Dashboards:** `python scripts/run_live_signals_ftmo.py` for ad-hoc visibility without the bot wrapper.
- **Health checks:** `python scripts/run_exec_mt5_smoketest.py --account_profile METAQUOTES_DEMO --dry_run` before live runs; `python scripts/run_minimal_ftmo_eval.py --step 10000` to confirm baseline edge.
- **Drift detection:** `python scripts/analyze_live_vs_sim.py --live_trades_csv data/live/latest.csv --sim_runs_csv results/minimal_ftmo_eval_runs.csv`.
- **Edge breakdowns:** `python scripts/analyze_trades.py --trades_path outputs/trades.csv --output results/trade_edge_map.csv`.
- **Legacy labs:** Monte-Carlo sweep helpers live in `scripts/legacy/`—not part of the daily loop.

## Nightly Data Maintenance
Run the bundled maintenance (reports + exports + sanity checks):
```bash
python scripts/run_daily_maintenance.py
```
This will:
- Generate the latest 6h quarterly report (latest session)
- Generate the latest 24h daily report (latest session)
- Refresh the 30d demo export bundle (CSV + behavior summary)
- Run the 72h sanity checker for HFT/safety rails
- Print the key output paths and a one-line sanity status
