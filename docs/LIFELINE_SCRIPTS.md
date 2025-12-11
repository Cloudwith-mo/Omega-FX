# Lifeline Scripts

Day-to-day operations use a small set of entry points. Everything else (Monte-Carlo sweeps, capital ladders, lab experiments) now lives under `scripts/legacy/`.

- **Autopilot**: `python scripts/run_autopilot.py --bot demo_trend_mr_london` (loads bot YAML → MT5 credentials → live signal CSV/alerts).  
  For manual monitoring without bot context, `python scripts/run_live_signals_ftmo.py`.
- **API / Alerts**: `uvicorn adapters.api_server:get_api_app` (FastAPI optional install). Telegram stubs live in `adapters/telegram_bot.py` for webhook-style alerts.
- **Dashboards & analysis**: `scripts/analyze_live_vs_sim.py` (live vs sim drift), `scripts/analyze_trades.py` (tagged trade edges), `scripts/run_eval_profile.py` / `scripts/run_ftmo_eval_sim.py` (eval health).
- **Maintenance & safety**: `scripts/run_exec_mt5_smoketest.py` (connectivity/risk gate), `scripts/run_minimal_ftmo_eval.py` + `scripts/run_backtest.py` (sanity checks), `scripts/run_exec_mt5_demo_from_signals.py` / `scripts/run_exec_sim_from_signals.py` (routing drills).
- **Data / exports**: `scripts/prepare_mt5_data.py` (normalize MT5 CSVs), `scripts/download_fx_api_data.py` (API exports), `scripts/download_example_data.py` (playground data only).
- **Legacy lab shelf**: Monte-Carlo/capital-plan sweep scripts were moved to `scripts/legacy/` (`run_capital_plan_sim.py`, `run_capital_surface_ftmo.py`, `run_capital_policy_compare.py`, `run_campaign_*`, `run_entry_mode_sweep.py`, `run_horizon_sweep.py`, `run_period_sweep.py`, `run_risk_*_sweep.py`).
