# Capital Plan Scenarios (FTMO preset, v1.1)

Baseline assumptions:
- Eval odds sampled from `results/minimal_ftmo_eval_runs.csv` (M15_WITH_H1_CTX, FULL risk, 2 positions, ~75 % pass rate).
- Funded payouts sampled from `results/funded_payout_ftmo_12m_runs.csv` (100 k FUNDED preset).
- Payouts are split 50 % withdraw / 50 % reinvest per plan unless stated.
- Bankroll floor is enforced by the risk budget fraction; once a wave would breach the allocation, no further evals launch.

All plans use 20 000 Monte-Carlo campaigns. Summary JSON/CSV artifacts live under `results/capital_plan_ftmo_*`.

## Plan A – Balanced 100k
- **Params:** 12 months, 2 evals per monthly wave, $300 fee, $1 k bankroll, risk budget fraction 0.6, reinvest 50 %.
- **Results:** mean payout **$8.2 k**, median $7.4 k, P(≥$10 k)=31 %, P(≥$50 k)=0 %.
- **Time to payouts:** median 5 months to $5 k, 7 months to $10 k.
- **Bankroll:** cost per wave equals the risk budget → every campaign eventually hits the bankroll floor (`prob_any_bankroll_breach = 1.0`). Only two evals launch before you’re “out of ammo.”
- **Takeaway:** Safest in terms of eval outlay but rarely exceeds $10 k/year; bankroll is exhausted immediately so reinvestment is the only fuel.

## PLAN_B_FTMO_FEEDERS (Recommended baseline)
- **Parameters:**  
  - `firm = FTMO_CHALLENGE`  
  - `initial_bankroll = 600`  
  - `eval_fee = 50` (FTMO 15k-style feeders)  
  - `months = 12`  
  - `evals_per_wave = 4`  
  - `waves_per_month = 1`  
  - `risk_budget_fraction = 0.7`  
  - `reinvest_fraction = 0.5`  
  - `eval_runs = results/minimal_ftmo_eval_runs.csv`  
  - `funded_runs = results/funded_payout_ftmo_12m_runs.csv`
- **Rationale:** $200 per wave stays inside the 70 % risk budget ($420) so wells of evals keep firing without overextending cash. Splitting payouts 50/50 balances personal withdrawals with bankroll growth, letting the operator scale without injecting new capital.
- **Expected performance (v1.1 sim):** mean payout ≈ **$33 k**, median ≈ $31 k, P(≥$10 k)=~98 %, P(≥$50 k)=~10 %, median 3 months to $5 k / 5 months to $10 k.
- **Execution guide:** See [PLAN_B_OPERATOR_GUIDE.md](PLAN_B_OPERATOR_GUIDE.md) for the month-by-month workflow and bankroll rules.
- **Status:** This is the **default plan to run** unless bankroll or risk appetite changes. Treat all other plans as experimental variations.

## PLAN_D_FTMO_HIGH_AMBITION (Lab-only)
- **Goal:** Stage from low-cost feeders into 100 k evals to chase ~$100 k in payouts within 12 months.
- **Mechanics:**
  - Stage 1 (months 0–6): launch only feeder evals (default $50).  
  - Stage 2 unlocks once withdrawn payouts ≥ `$plan_d_stage2_trigger` (default $10 k) or month ≥ 6. Once active, each wave shifts a configurable fraction (default 50 %) of the slots to 100 k evals (`large_eval_fee`, default $350).
  - Waves still obey `risk_budget_fraction × bankroll`. If a wave cannot be funded safely, it is skipped.
- **How to explore:**  
  - Single configuration: `python scripts/run_capital_plan_sim.py --plan_mode PLAN_D ...`  
  - Grid sweep / $100k ambition surface: `python scripts/run_capital_surface_ftmo.py` (outputs `results/capital_surface_ftmo_plan_d_12m.csv`).
- **Notable candidates (all from `capital_surface_ftmo_plan_d_12m.csv`, 10k sims each):**
  1. **Starter ambition:** `initial_bankroll=5k`, `evals_per_wave=6`, `waves_per_month=2`, `reinvest_fraction=0.5` → mean payout ≈ $259 k, median ≈ $258 k, `P(total ≥ 100k) ≈ 1.0`, `P(net loss)=0`, median ~2.5 months to first $5 k, ~3.1 months to $10 k.
  2. **Higher firepower:** `initial_bankroll=10k`, `evals_per_wave=6`, `waves_per_month=2`, `reinvest_fraction=0.5–0.7` → mean payouts $186–310 k, `P(total ≥ 100k) ≈ 1.0`, zero net-loss campaigns.
  3. **Conservative waves:** `initial_bankroll=5k`, `evals_per_wave=4`, `waves_per_month=2`, `reinvest_fraction=0.5` → mean payout ≈ $192 k, `P(total ≥ 100k) ≈ 0.9998`.
- **Caveats:** Every PLAN_D configuration in the sweep spends the entire bankroll (`p_bankroll_breach = 1`). These are high-ambition lab setups—only run them if you accept full bankroll deployment and higher operational load.

## PLAN_E_FTMO_HYBRID (Intermediate rung)
- **Goal:** Let a small bankroll ($1.5k) climb the ladder by running feeders in Stage 1, then automatically mixing in 100 k evals once profits allow it.
- **Parameters:** `initial_bankroll=1.5k`, `evals_per_wave=4`, `waves_per_month=2`, feeder fee $50, large fee $350, `plan_d_stage2_trigger=10k`, `plan_d_stage1_month_limit=6`, `risk_budget_fraction=0.7`, `reinvest_fraction=0.5`.
- **12 m stats** (`results/capital_plan_ftmo_plan_e_hybrid_12m_summary.json`):
  - mean payout **$111k**, median **$110k**
  - `P(total ≥ 10k)=100%`, `P(total ≥ 50k)=99.85%`, `P(total ≥ 100k)=66.78%`
  - median time to $5k ≈ 3 months, to $10k ≈ 4 months
- **6 m stats** (`results/capital_plan_ftmo_plan_e_hybrid_6m_summary.json`): mean **$52k**, median **$51k**, `P(total ≥ 50k)=54%`.
- **Interpretation:** Plan E is the natural “step 2” after Plan B—once feeders spit out ~$10k, recycle $1.5k into this hybrid to target $50k+ within half a year and $100k+ within a year. Bankroll breaching still occurs (the whole $1.5k is deployed), so treat it as an intermediate step before unleashing Plan D.

## Policy comparison (B→D vs B→E→D vs BE3-early)

- `scripts/run_capital_policy_compare.py` now evaluates all three escalation policies for 12 months with 20k Monte-Carlo campaigns each (artifacts in `results/capital_plan_ftmo_plan_*` plus the aggregate `results/capital_plan_ftmo_policy_compare.json`).

| Policy | Mean / Median payout | `P(≥50k)` / `P(≥100k)` | `P(net loss)` | Median months to $10k | Notes |
| --- | --- | --- | --- | --- | --- |
| PLAN_BD_DIRECT | $286k / $286k | 99.99% / 99.98% | 0% | 4 | Plan B (feeders) until $10k withdrawn, then deploy $5k into Plan D. |
| PLAN_BED_LADDER | $343k / $343k | 99.99% / 99.98% | 0% | 4 | Insert Plan E once Plan B hits $10k, promote to Plan D at $25k total withdrawals. |
| PLAN_BE3_EARLY | **$397k / $397k** | **99.99% / 99.99%** | 0% | 4 | Earlier promotions: Plan E unlocks after $6.5k from Plan B, Plan D at $15k combined (all funded from profits). |

- **PLAN_BD_DIRECT:** same behavior as before—Plan B feeds Plan D once it has $10k of realized profit, using a $5k profit pool allocation. Still zero net-loss probability thanks to the low feeder cost.
- **PLAN_BED_LADDER:** matching the documented ladder (B → E at $10k, D at $25k). Provides a ~20% bump in mean payouts vs going straight to Plan D by giving profits more time to compound in the hybrid stage.
- **PLAN_BE3_EARLY:** earlier promotions keep capital recycling faster (Plan E lights up at $6.5k, Plan D at $15k). This produces the fattest right tail (median ≈ $397k, `P(≥100k)=99.99%`) without increasing the left-tail risk, but assumes you are comfortable pushing profits hard as soon as they appear.
- **Takeaway:** All three policies keep the “worse than $600” probability at 0 %. If the goal is simply “hit $50k–$100k ASAP,” the early ladder (BE3) dominates. If you want a slower ramp with more time observing Plan E before introducing 100k evals, stay with the existing ladder (B → E → D). Only choose the direct B → D policy if you prefer skipping the intermediate hybrid entirely.

## Plan C – Aggressive 100k
- **Params:** Same as Plan A but 4 evals per wave, risk budget fraction 0.8.
- **Results:** No waves launch (cost $1.2 k > $800 risk cap). All metrics stay at zero.
- **Takeaway:** Simply infeasible for a $1 k bankroll; you’d need either a larger bankroll or smaller eval fees.

## Recommendations
- **Most bankroll-safe:** Plan A still caps out the real-dollar exposure but also stalls near $8 k/year—use it only for sandbox purposes.
- **Default:** Plan B feeders (plus the operator guide) remains the canonical deployable plan for a $600 bankroll.
- **Intermediate growth:** Once Plan B realizes ~$10k, recycle $1.5k into Plan E to chase $50k+ without jumping straight to Plan D.
- **High ambition:** Plan D (or the laddered B→E→D policy) is how you push for $100k+—just accept that the bankroll will be fully deployed for most of the year.
- **Too aggressive:** Plan C is still infeasible at small bankrolls. Use Plan E to bridge the gap instead.

Next steps: rerun the simulator whenever eval/funded presets change, or when you adjust bankroll, reinvest fraction, or wave size. Launch playbooks now reference this doc so the capital plan remains in sync with the trading engine.
