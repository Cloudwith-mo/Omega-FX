# Monitoring Workflow

- **Start the bot**: `python scripts/run_autopilot.py --bot demo_trend_mr_london` (canonical call). This logs signals to `results/autopilot_demo_trend_mr_london_signals.csv` and prints alert stubs.
- **Dashboards**: For ad-hoc visibility, `python scripts/run_live_signals_ftmo.py` still emits the same CSV/console alerts without the bot wrapper.
- **Health checks**: Run `python scripts/run_exec_mt5_smoketest.py --account_profile METAQUOTES_DEMO --dry_run` before live sessions; use `python scripts/run_minimal_ftmo_eval.py --step 10000` to confirm baseline edge.
- **Drift detection**: After a session, compare live vs sim:  
  `python scripts/analyze_live_vs_sim.py --live_trades_csv data/live/latest.csv --sim_runs_csv results/minimal_ftmo_eval_runs.csv`
- **Edge breakdowns**: `python scripts/analyze_trades.py --trades_path outputs/trades.csv --output results/trade_edge_map.csv` to see which sessions/volatility regimes are carrying performance.
- **Legacy labs**: Monte-Carlo sweep helpers now sit in `scripts/legacy/`—they are not part of the daily monitoring loop.
