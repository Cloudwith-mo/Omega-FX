# Omega FX – Firm Comparison (Eval + 100k Funded Baselines)

## Evaluation Baselines (Entry = M15_WITH_H1_CTX, FULL risk preset)
_8-run challenge sweeps with step=10,000 (fewer runs but keeps runtime manageable)._

| Firm        | Pass Rate | Mean Return | Max Daily Loss | Max Trailing DD | Mean Trades/Run |
|-------------|-----------|-------------|----------------|-----------------|-----------------|
| FTMO        | **75.0%** | 8.4%        | 2.00%          | 7.33%           | 325             |
| FundedNext  | 62.5%     | 6.2%        | 2.18%          | **6.03%**       | 251             |
| Aqua Instant| 62.5%     | 6.2%        | 2.18%          | **6.03%**       | 251             |

Key notes:
- FTMO’s higher prop caps (5%/10%) let the same engine press harder → +12–13 percentage points better pass rate.
- FundedNext & Aqua share the same guardrails, so their eval distributions match.

## Funded Payout Baselines (Entry = M15_WITH_H1_CTX, FUNDED tier scales, max_pos=1)
_Monte-Carlo with 30 target windows per horizon, step=5,000. Resulting run counts are 16 (6 m) and 18 (12 m)._

### 6-Month Campaign (100k account)

| Firm        | Avg Total Payout | Median Total | Mean Monthly | P(≥10k total) | P(≥20k total) | P(≥1 payout ≥5k) | P(Account Death) | Mean Days to 1st Payout |
|-------------|-----------------|--------------|--------------|---------------|---------------|------------------|------------------|--------------------------|
| FTMO        | $6.3k           | $5.1k        | $1.05k       | 25%           | 0%            | 0%               | 0%               | 24 days                  |
| FundedNext  | $6.3k           | $5.1k        | $1.05k       | 25%           | 0%            | 0%               | 0%               | 24 days                  |
| Aqua Instant| $6.3k           | $5.1k        | $1.05k       | 25%           | 0%            | 0%               | 0%               | 24 days                  |

### 12-Month Campaign (100k account)

| Firm        | Avg Total Payout | Median Total | Mean Monthly | P(≥10k total) | P(≥20k total) | P(≥1 payout ≥5k) | P(Account Death) | Mean Days to 1st Payout |
|-------------|-----------------|--------------|--------------|---------------|---------------|------------------|------------------|--------------------------|
| FTMO        | $10.9k          | $8.8k        | $0.91k       | 33%           | 11%           | 5.6%             | **0%**           | 23 days                  |
| FundedNext  | $10.1k          | $8.1k        | $0.84k       | 33%           | 11%           | 5.6%             | 16.7%            | 23 days                  |
| Aqua Instant| $10.1k          | $8.1k        | $0.84k       | 33%           | 11%           | 5.6%             | 16.7%            | 23 days                  |

## Recommendations

1. **Anchor on FTMO.** Higher eval pass rate (+75%) and zero account deaths in funded sims make it the most forgiving while still producing ~$900/month median payouts per 100k account.
2. **FundedNext as backup.** Eval odds match Aqua, but funded sims show a small (17%) failure risk over 12 months—acceptable if you want immediate 3%/6% caps that mirror FundedNext’s real challenge.
3. **Aqua Instant = opportunistic.** Stats mirror FundedNext but without the eval sample size; treat it as an instant-liquidity add-on once FTMO/FundedNext pipelines are humming.

Operational caveats:
- These baselines use trimmed challenge samples (step=10k for evals, 30 windows for funded sims). Expect sampling noise; re-run the scripts after each strategy/risk change.
- Payout odds assume FUNDED tier scales (A=1.0/B=0.5) and single-position mode. Scaling risk back up or allowing more concurrent trades will shift both payout and death probabilities—rerun the sims before changing production presets.

### Campaign-Level Scenarios

For multi-eval campaigns, see `docs/CAMPAIGN_SCENARIOS.md` (Strategy A: single 4×100k batch, Strategy B: 8×50k feeders → up to 4×100k evals). It details:

- Mean/median payouts for 6 m and 12 m horizons.
- P(total ≥ $10k / $50k / $100k), probability of zero payouts, and monthly trajectories.
- Why Strategy B (escalation) offers the best shot at $50k+ while keeping risk comparable to the simpler one-batch strategy.
