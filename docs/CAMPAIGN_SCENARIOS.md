## FTMO Campaign Scenarios (deploy preset)

Baseline assumptions:
- Eval stats sampled from `results/ftmo_eval_runs.csv` (M15_WITH_H1_CTX deploy preset, ~67% pass rate, avg 32 trading days to pass).
- Funded payouts sampled from the 100k FUNDED preset Monte-Carlo windows (`results/funded_payout_ftmo_{6m,12m}_runs.csv`). Payout lists are truncated if an eval finishes late in the campaign window.
- Strategy B reuses the same eval distribution for the initial 50k tier due to lack of separate data; risk/guardrails stay percent based, so the approximation is conservative.

### Scenario Summary

| Strategy | Horizon | Mean Payout | Median Payout | P(≥10k) | P(≥50k) | P(≥100k) | P(No Payout) | P(Account Death) |
|----------|---------|-------------|---------------|---------|---------|----------|--------------|------------------|
| A: 4×100k evals at t=0 | 6 months | $16.5k | $15.3k | 69.8% | 0.25% | 0% | 1.8% | 0% |
| A: 4×100k evals at t=0 | 12 months | $29.1k | $26.5k | 85.2% | 12.7% | 0.07% | 2.7% | 0% |
| B: 8×50k → up to 4×100k evals | 6 months | $15.4k | $13.9k | 65.1% | 0.46% | 0% | 1.9% | 0% |
| B: 8×50k → up to 4×100k evals | 12 months | **$38.1k** | **$35.4k** | **91.5%** | **26.8%** | **1.1%** | **1.4%** | 0% |

### Monthly Trajectories

- **Strategy A (6m):** Most payouts cluster in months 3–5 once the initial eval batch clears. Mean cumulative climbs to ~$16k by month 6; p90 stays below $31k, so six months is not enough to target $100k.
- **Strategy A (12m):** Median cumulative hits ~$26.5k by month 12; only 0.07% of campaigns crest $100k.
- **Strategy B (12m):** Escalation produces thicker tails—median crosses $35k by month 12, p90 nears $68k, and ~1.1% of runs exceed $100k. Early months are thin (most payouts land after month 4 once 100k evals spin up).

### Takeaways

1. **Best payout vs. risk:** Strategy B over 12 months dominates—higher mean/median, 91% chance of beating $10k, and ~27% chance of beating $50k, while maintaining <1.5% chance of zero payouts and zero observed account deaths in the FUNDED sims.
2. **One-batch Strategy A** is simpler but stalls around $15k (6m) or $26k (12m) median. Use it when bankroll can’t support escalations, but expect to fall well short of the $100k annual goal.
3. **100k cumulative target:** Even the aggressive Strategy B only crosses $100k in ~1% of 12‑month campaigns. Hitting that target reliably will require either stacking multiple batches or pushing risk higher once realized gains are banked (per the later “floor + surplus” plan).
4. **Timeline guidance:** Most payouts begin after month 3 regardless of strategy—allocate budget so you can weather 2–3 months of little-to-no income while evals spin up.

See the corresponding JSON/CSV artifacts under `results/campaign_scenarios_ftmo_*.{json,csv}` for the full probability distributions, monthly means, and cumulative curves.
