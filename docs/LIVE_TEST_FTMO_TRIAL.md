# FTMO Trial Field-Test Kit

This playbook bridges the Ω-FX lab and a manual FTMO free trial. It explains how to spin up a sandbox account, run the live signal harness, and check live performance against the simulation distribution before you spend money on paid evals.

## 1. Trial & MT5 Setup

1. Request an FTMO free trial and download the corresponding MT5 terminal.
2. Log into the trial account inside MT5 (no automation yet—Ω-FX only listens for data).
3. Install Python dependencies and activate the repo’s virtualenv:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. (Optional) Set environment variables if your MT5 terminal requires explicit credentials; the `MetaTrader5` Python package will reuse the last logged-in account by default.

## 2. Run the live signal harness

Every M15 bar, pull the latest market data and write signal suggestions to CSV:

```bash
source .venv/bin/activate
python scripts/run_live_signals_ftmo.py \
  --firm FTMO_CHALLENGE \
  --symbols EURUSD GBPUSD USDJPY \
  --alert_mode telegram
```

- Output CSV: `outputs/live_signals_ftmo.csv` (appends one row per signal).
- `--firm` selects the firm profile in case you ever mirror FundedNext/Aqua later.
- `--alert_mode` currently prints formatted lines to stdout; swap to `none` for silent logging, or keep `telegram/slack` as placeholders until the webhook plumbing is added.

## 3. Daily operator loop (manual shadow trading)

1. Schedule the command above to run just after each M15 close (e.g., cron job or manual timer).
2. After every run:
   - Read the last rows of `outputs/live_signals_ftmo.csv`.
   - For each signal, optionally sanity-check context (news, spreads).
   - Manually place the trade on the FTMO trial with the provided direction, stop, take-profit, and target risk fraction.
3. Track live equity vs the FTMO caps:
   - Max daily loss: 5% (FTMO profile uses 3% internal guard, but adhere to prop cap).
   - Max trailing drawdown: 10%.
4. If a signal looks off (spreads widen, macro data release, etc.), skip it—log the reason in your personal journal so you can reconcile later.

## 4. Weekly routine: export + analyze

1. In MT5, open the account history tab → select the last 7 days → right-click → “Save as Detailed Report” (CSV).
2. Drop the file into `data/live/ftmo_trial_YYYYMMDD.csv`.
3. Compare the live results to the Ω-FX simulation distribution:
   ```bash
   source .venv/bin/activate
   python scripts/analyze_live_vs_sim.py \
     --live_trades_csv data/live/ftmo_trial_20250112.csv \
     --sim_runs_csv results/minimal_ftmo_eval_runs.csv \
     --account_size 100000 \
     --output_json results/live_vs_sim_ftmo_trial_summary.json
   ```
   - Optional: add `--output_report docs/live_vs_sim_ftmo_trial_20250112.md` for a markdown snippet you can paste into the trading journal.
   - For offline smoke tests, a sample MT5 export lives at `data/examples/ftmo_trial_sample.csv`.
4. Review the analyzer output:
   - Total return %, hit rate, number of trades.
   - Max daily loss / max trailing DD vs the lab distribution percentiles.
   - Flags whenever live drawdowns sit in the worst 5% of sims or returns lag behind expectations.
5. Archive the CSV and analyzer JSON/markdown together. Re-running the analyzer after each tweak (tier changes, new regime filter) keeps you honest.

## 5. Graduation criteria before buying evals

- At least 2 consecutive weeks of FTMO trial data.
- Live-vs-sim analyzer shows drawdowns within the 50th–80th percentile of sims (i.e., not worse than the median lab path).
- Daily operator loop feels smooth (no missed signals, manual execution manageable).
- Capital plan preference chosen (e.g., Plan B feeders) so you can map FTMO results onto campaign-level expectations.

When those conditions are satisfied, re-run the README “Sanity Check” commands, review the latest plan stats in `docs/CAPITAL_PLAN_SCENARIOS.md`, and only then start paying for evals.
