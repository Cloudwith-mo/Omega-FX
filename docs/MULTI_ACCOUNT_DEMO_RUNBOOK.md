# Multi-Account Demo Runbook

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

## Logs & summaries
- Per-bot logs: `logs/autopilot/<bot>.csv`
- Per-bot summaries: `logs/autopilot/<bot>_summary.json`

Bots started:
- demo_trend_only
- demo_mr_only
- demo_session_only
- demo_trend_mr_london
