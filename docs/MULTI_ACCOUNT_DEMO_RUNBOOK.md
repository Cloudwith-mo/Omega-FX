# Multi-Account Demo Runbook

## Prereqs
- Four MT5 demo terminals installed (one per bot). Map each terminal path/account into `config/mt5_accounts.yaml` under `DEMO_TREND`, `DEMO_MR`, `DEMO_SESSION`, and `DEMO_MULTI` (placeholders are present—replace logins/passwords/paths locally).
- Activate the project venv (`source .venv/bin/activate`) and install optional deps (`fastapi`, `uvicorn`, `requests`) if you want API/alert adapters.
- Symbols funded in each terminal: EURUSD, GBPUSD, USDJPY, XAUUSD.

## Quick commands
- **Smoke test (~6 minutes):**
  ```bash
  python scripts/run_all_demo_bots.py --hours 0.1 --sleep-seconds 30
  ```
- **Full trading day (24h):**
  ```bash
  python scripts/run_all_demo_bots.py --hours 24 --sleep-seconds 60
  ```
- **Stop all bots:** Ctrl+C (the runner terminates child processes).

## Quick Start Tonight
1) Activate venv:
```bash
source .venv/bin/activate
```
2) Start all four demo bots for an overnight burn:
```bash
python scripts/run_all_demo_bots.py --hours 8
```
3) MT5 daily check (once in the morning):
   - Each terminal shows connected (no “invalid account”).
   - Positions match the Alpha Cockpit dashboard for each bot.
4) Evening dashboard check:
   - Filter by bot_id and confirm trades/PNL for the day look sane.
   - No bot exceeds daily loss / per-trade risk thresholds.

## Start all bots
```bash
source .venv/bin/activate
python scripts/run_all_demo_bots.py
```

## Start one bot
```bash
source .venv/bin/activate
python scripts/run_autopilot.py --bot demo_trend_mr_london
```

## Monitor
- Alpha Cockpit / existing dashboards.
- Dashboards should show `bot_id` and `mt5_account_alias` in the header; use the bot filter dropdown to switch between “All bots” and each bot_id.
- `logs/autopilot/<bot_id>.log` for stdout/stderr from each bot.
- MT5 mobile/terminal to watch fills and connection status.
- Sanity checker: `python scripts/run_exec_mt5_smoketest.py --account_profile <bot_id> --dry_run` before a session.

## Stop
- CTRL+C in the terminal that launched the bots, or terminate individual PIDs from the summary printed by `run_all_demo_bots.py` (Task Manager/Activity Monitor).

## Weekend analysis checklist
- Export live trades and compare vs sim: `python scripts/analyze_live_vs_sim.py --live_trades_csv data/live/latest.csv --sim_runs_csv results/minimal_ftmo_eval_runs.csv`
- Tag edge review: `python scripts/analyze_trades.py --trades_path outputs/trades.csv --output results/trade_edge_map.csv`
- Risk profile recap: `python scripts/run_risk_profile_summary.py`
- Strategy readiness sanity: `python scripts/run_strategy_readiness_check.py --bot demo_trend_mr_london`

## Bots started by the launcher
- demo_trend_only
- demo_mr_only
- demo_session_only
- demo_trend_mr_london
