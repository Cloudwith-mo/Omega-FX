# Prop Eval Mode

Prop-eval runs should lean on the bot profiles instead of a pile of CLI flags.

- Canonical kick-off: `python scripts/run_autopilot.py --bot demo_trend_mr_london`
- For a conservative eval posture, use the low-risk preset: `python scripts/run_autopilot.py --bot prop_eval_low_risk`
- Bot YAMLs live under `bots/`; each defines the target MT5 account alias, firm profile, and strategy risk scales. Update those YAMLs instead of hand-editing scripts.
- Optional overrides remain available (`--firm_profile`, `--account_profile`, `--symbols`) but default to the bot configuration.
- Outputs land in `results/autopilot_<bot>_signals.csv`; use `scripts/analyze_live_vs_sim.py` to validate live vs sim drift after a session.
