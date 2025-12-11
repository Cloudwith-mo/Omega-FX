# PLAN_B_FTMO_FEEDERS – Operator Guide

This is the “load once, run for a year” playbook for the default FTMO capital plan. It assumes the minimal M15_WITH_H1_CTX preset and the campaign stats in `results/capital_plan_ftmo_plan_b_feeders_final_summary.json`.

## Capital Inputs

- **Starting bankroll:** $600 (cash earmarked for eval fees)
- **Eval cost:** $50 per feeder (approx FTMO 15k Lite)
- **Risk budget fraction:** 0.7 (max $420 exposure per wave)
- **Waves per month:** 1
- **Evals per wave:** 4
- **Reinvest rule:** Withdraw 50% of every payout, reinvest the remaining 50% back into the bankroll.
- **Stop rule:** Never launch a wave if `wave_cost = evals_per_wave × eval_fee` exceeds either:
  - `risk_budget_fraction × current_bankroll`, or
  - `current_bankroll` itself.
  If that happens, the campaign is considered out of ammo—pause and reassess.
- **Bankroll floor:** $0 (because we treat the full $600 as committed capital). If you want a higher floor, raise `initial_bankroll` or lower wave size.

## Month-by-Month (first 6 months)

| Month | Actions | Notes |
|-------|---------|-------|
| 1 | Buy 4 evals ($200). Start all on day 1. Track each eval’s equity vs. time. | Use `run_minimal_ftmo_eval.py --step 10000` first to ensure the preset is behaving. |
| 2 | Launch the next wave of 4 evals ($200) **only if** payouts/reinvestments have restored the bankroll ≥ $200 and the risk budget check passes. Otherwise, skip the wave and conserve bankroll. | Expect some evals to still be running from wave 1; do not exceed 4 concurrent evals unless reinvested capital permits. |
| 3 | By now, at least one funded account should have produced a payout (median 3 months to $5k). Withdraw 50% of each payout, reinvest the other 50% immediately. Continue launching monthly waves if the bankroll supports it. | If an eval reaches +10% before 20 trading days, stop it and prepare the funded account. |
| 4 | Re-run `scripts/legacy/run_capital_plan_sim.py` with updated bankroll if you made manual deviations (e.g., paused waves). Launch wave 4 only if the bankroll ≥ $200 and the risk check passes. | |
| 5 | Keep the 20-day timebox: if an eval has not passed by trading day 20 (≈ 1 month), treat it as a soft fail and stop monitoring it. Launch the next wave only after clearing the risk budget check. | |
| 6 | Take stock: compare real payouts vs. the simulator’s median ($31k by month 12). If payouts lag badly, consider pausing new evals until existing funded accounts catch up. | |

Repeat the same logic through month 12. The simulator’s median path reaches ~$31k withdrawn by month 12 with roughly 8 evals launched in total (one wave per month).

## Eval Handling

- **Before buying:** Run `python scripts/run_minimal_ftmo_eval.py --step 10000` to confirm the core preset still yields ~70–75% pass rate and ≤2% max daily loss.
- **During evals:** Time-box at 20 trading days. Hard-stop any eval that:
  - Hits +10% (success),
  - Breaks firm/internal risk rules (failure),
  - Stagnates inside –3% to +5% after 20 trading days (soft fail).
- **After pass:** Immediately convert the funded account into the FUNDED preset and log payouts using the 50/50 rule.

## Reinvest & Withdraw Rules

- For every funded payout:  
  `withdraw_amount = payout × 0.5`  
  `reinvest_amount = payout × 0.5`
- Withdrawn cash is real profit; do not recycle it unless your external plan demands it.
- Reinvested cash increases the bankroll for future waves. Always re-run the risk-budget check before launching the next wave.

## Monitoring & Health Checks

1. **Monthly sanity check:**  
   `python scripts/legacy/run_capital_plan_sim.py --firm FTMO_CHALLENGE --months 12 --evals_per_wave 4 --waves_per_month 1 --eval_fee 50 --initial_bankroll <current_bankroll> --risk_budget_fraction 0.7 --reinvest_fraction 0.5 --eval_runs results/minimal_ftmo_eval_runs.csv --funded_runs results/funded_payout_ftmo_12m_runs.csv --funded_horizon_months 12 --output results/capital_plan_ftmo_plan_b_feeders_final_summary.json --output_runs results/capital_plan_ftmo_plan_b_feeders_final_runs.csv`

2. **Before each batch of eval purchases:**  
   Confirm `wave_cost ≤ risk_budget_fraction × bankroll` (e.g., $200 ≤ 0.7 × $current_bankroll). If not, skip the wave.

3. **Stopping condition:**  
   - If aggregate withdrawals reach your yearly goal (e.g., $30k), optionally pause new evals and consolidate.  
   - If bankroll < wave cost for two consecutive months, treat the campaign as spent; either inject new capital or retire the plan.

## Success & Failure Criteria

- **Success (6–12 months):**  
  - Withdrawals within 10–12 months align with the simulator’s median (~$31k).  
  - No wave launched without enough bankroll to cover the full wave safely.  
  - Bankroll trending upwards due to reinvestment.

- **Failure modes:**  
  - Wave costs exceed bankroll (violated risk check).  
  - Evals routinely hit 20-day limit without passing (reevaluate the trading preset before continuing).  
  - Bankroll depleted because payouts were fully withdrawn instead of splitting 50/50—plan stalls early.

Follow this guide verbatim to keep Plan B disciplined, repeatable, and aligned with the automation results. If you change any major parameter (bankroll, eval size, reinvest fraction), rerun the simulator and update this document before launching new waves.
