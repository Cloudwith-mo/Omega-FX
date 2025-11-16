# Omega FX – Funded Playbook

> For the overarching design principles behind these presets, see [OMEGA_TRADING_PHILOSOPHY.md](OMEGA_TRADING_PHILOSOPHY.md).

## Funded Profiles (Account Phase = FUNDED)

| Firm        | Entry Mode         | A/B/UNKNOWN Scales | Internal Caps (daily / trailing) | Max Positions |
|-------------|-------------------|--------------------|-----------------------------------|---------------|
| FTMO        | `M15_WITH_H1_CTX` | 1.0 / 0.5 / 0.3    | 2.5% / 7% (mirrors 5% / 10% prop) | 1             |
| FundedNext  | `M15_WITH_H1_CTX` | 1.0 / 0.5 / 0.3    | 2.2% / 5% (mirrors 3% / 6% prop)  | 1             |
| Aqua Instant| `M15_WITH_H1_CTX` | 1.0 / 0.5 / 0.3    | 2.2% / 5%                          | 1             |

- The FUNDED presets apply ~30–35% less A-tier risk than the eval versions and force single-position mode to protect realized gains.
- Guardrails inherit the active firm profile (3%/6% or 5%/10%); internal caps stay well inside those.

## Running the Funded Payout Simulator

Use `scripts/run_funded_payout_sim.py` to Monte-Carlo payout schedules:

```bash
python scripts/run_funded_payout_sim.py \
  --firm ftmo \
  --months 6 \
  --num_runs 200 \
  --account_size 100000 \
  --payout_split 0.7 \
  --payout_interval_days 20 \
  --ratchet_fraction 0.05
```

This script:

1. Uses the FUNDED profile (entry mode, tier scales, guardrails).
2. Slides a 6-month trading window across the MT5 portfolio data.
3. Runs `run_backtest` for each window with `account_phase="FUNDED"`.
4. Applies a payout policy:
   - Withdraw `payout_split` of gains every `payout_interval_days`.
   - Trigger an extra withdrawal whenever equity is ≥ `ratchet_fraction` above the protected “floor”.
5. Records per-run totals, largest payout, time to first payout, and whether the account “dies” (internal stop or prop fail).

Outputs land in:

- `results/funded_payout_<firm>_<months>m_runs.csv` – raw per-run stats.
- `results/funded_payout_<firm>_<months>m_summary.json` – aggregated probabilities (P≥$5k payout, cumulative ≥$10k/$20k/$50k, survival rate, average time to first payout).

### Interpreting the Summary JSON

- `avg_total_payout`, `median_total_payout`, `p10/p90_total_payout` — distribution of cumulative withdrawals.
- `prob_at_least_one_payout`, `prob_single_payout_ge_5k` — odds of collecting meaningful checks.
- `mean_time_to_first_payout` — how long (in trading days) it usually takes to lock the first payout.
- `prob_account_death` — chance the account violates firm rules within the horizon.

## Lab → Eval → Funded Bridge

1. **Lab (high-octane):** Use the research presets (A-scale 0.8, daily cap 2.2%, max_pos=2) to test new edges.
2. **Eval:** Run `python scripts/run_eval_profile.py --firm <firm>` before every eval purchase to confirm pass-rate, risk, and guardrails.
3. **Funded:** After a pass, switch to the FUNDED presets and run the payout simulator for the relevant firm and horizon (3–12 months). Use the JSON output to plan bankroll allocation, expected payout cadence, and acceptable drawdowns.

Keep the FUNDED simulator handy whenever you tweak risk tiers or payout rules—the goal is not just to pass an eval once, but to sustain a series of payouts without ever breaching the firm caps.
