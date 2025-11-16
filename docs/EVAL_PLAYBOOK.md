# Omega FX – Evaluation Playbook

> For the overarching design principles behind these presets, see [OMEGA_TRADING_PHILOSOPHY.md](OMEGA_TRADING_PHILOSOPHY.md).

## Baseline Configuration (Phase 3)
- Entry mode: `M15_WITH_H1_CTX`
- Risk preset: `FULL`
- Firm profile (default): `TIGHT_PROP` (FundedNext-style, 3% daily / 6% total)
- Max concurrent positions: 2 (enforced by risk budget + per-day cap)
- Risk tiers: unchanged (A-tier 0.6% base risk × tier scale)

### One-Command Eval Check
Every firm now has a bundled evaluation profile (`ACCOUNT_PHASE_PROFILES[firm]["EVAL"]`) that locks in:

- Firm risk caps (e.g., FTMO → 5%/10%, FUNDEDNEXT → 3%/6%).
- Entry mode (`M15_WITH_H1_CTX`), tier scales, and `MAX_CONCURRENT_POSITIONS`.

Run a sanity check before purchasing an eval:

```bash
python scripts/run_eval_profile.py --firm ftmo
```

This calls `run_challenge_sim.py` with the FTMO evaluation preset, writes `results/eval_profile_ftmo.json`, and prints:

- pass_rate / mean + median return
- max_daily_loss / max_trailing_dd
- mean trades per run + per symbol

Use `--firm fundednext` or `--firm aqua` for the other presets.

For the FTMO deployment preset specifically, run:

```bash
python scripts/run_ftmo_eval_sim.py --step 10000
```

This enforces the final “go-to-market” configuration (M15_WITH_H1_CTX, FULL risk scales, 2 concurrent positions) and writes `results/ftmo_eval_deploy_profile_summary.json` so you can sanity-check pass rate, return stats, and per-symbol trade counts before triggering a new eval.

### Portfolio Stats
| Firm Profile | Pass Rate | Mean Return | Max Daily | Max Trailing | Mean Trades/Run |
|--------------|-----------|-------------|-----------|--------------|-----------------|
| TIGHT_PROP   | **62.5%** | 6.4%        | 2.20%     | 6.03%        | 283.9           |
| LOOSE_PROP   | **67.5%** | 8.1%        | 2.92%     | 8.60%        | 378.0           |

## Time-Boxed Pass Rates (M15)
| Firm | Horizon (days) | Pass Rate | Mean Return | Trades/Run | Max Daily | Max DD |
|------|----------------|-----------|-------------|------------|-----------|--------|
| TIGHT_PROP | 5  | 0%   | 0.6% | 54 | 2.16% | 6.03% |
| TIGHT_PROP | 10 | 0%   | 2.2% | 114 | 2.16% | 6.03% |
| TIGHT_PROP | 15 | 7.5% | 2.7% | 156 | 2.20% | 6.03% |
| TIGHT_PROP | 20 | 17.5%| 3.4% | 189 | 2.20% | 6.03% |
| LOOSE_PROP | 5  | 0%   | 0.6% | 54 | 2.24% | 8.60% |
| LOOSE_PROP | 10 | 0%   | 2.2% | 116 | 2.24% | 8.60% |
| LOOSE_PROP | 15 | 7.5% | 2.7% | 162 | 2.92% | 8.60% |
| LOOSE_PROP | 20 | 20%  | 3.8% | 202 | 2.92% | 8.60% |

## Campaign Odds (M15, TIGHT_PROP)
| # Evals | Fee (USD) | Pass ≥1 Eval | Mean Profit | Mean Time to First Pass |
|---------|-----------|--------------|-------------|-------------------------|
| 4       | 325       | **98.1%**    | \$24.2k     | 16.5 trading days       |
| 8       | 325       | **99.96%**   | \$48.3k     | 11.1 trading days       |
| 12      | 325       | ~100%        | \$72.5k     | 8.7 trading days        |

## Firm-Specific Profiles
| Firm | Internal Caps | Prop Caps | Pass Rate | Campaign Stats |
|------|---------------|-----------|-----------|----------------|
| FUNDNEDNEXT (default) | 2.2% daily / 5% trailing | 3% daily / 6% total | 62.5% | `results/campaign_stats_fundednext_m15.csv` |
| FTMO_CHALLENGE | 2.5% daily / 7% trailing | 5% / 10% | 67.5% | `results/campaign_stats_ftmo_m15.csv` |
| AQUA_INSTANT | 2.2% / 5% | 3% / 6% | 62.5% | `results/campaign_stats_aqua_m15.csv` |

## Period Robustness (available data windows)
| Period | Pass Rate | Mean Return | Max Daily | Max DD |
|--------|-----------|-------------|-----------|--------|
| 2021-11 → 2022-12 | 54.6% | 6.9% | 2.20% | 5.32% |
| 2023-01 → 2023-12 | 40.0% | 4.1% | 1.99% | 5.61% |
| 2024-01 → 2024-12 | 70.0% | 7.0% | 2.20% | 5.48% |

## Sensitivity (Quick sanity check, step=4000)
| A-scale | Daily Cap | Max Pos | Pass Rate | Max Daily | Max DD |
|---------|-----------|---------|-----------|-----------|--------|
| 0.6 | 1.8% | 1 | 20% | 1.34% | 4.14% |
| 0.6 | 1.8% | 2 | 45% | 1.77% | 5.24% |
| 0.6 | 2.2% | 1 | 20% | 1.34% | 4.14% |
| 0.6 | 2.2% | 2 | 45% | 1.99% | 5.52% |
| 0.8 | 1.8% | 1 | 20% | 1.23% | 4.52% |
| 0.8 | 1.8% | 2 | 50% | 1.77% | 5.40% |
| 0.8 | 2.2% | 1 | 20% | 1.23% | 4.52% |
| 0.8 | 2.2% | 2 | 50% | 1.99% | 5.52% |

## Recommended Usage
- **Lab Config:** Full risk (A-scale 0.8, daily cap 2.2%, max_pos=2) for research.
- **Eval Config:** Use `TIGHT_PROP`, A-scale 0.7 (default FULL preset), daily cap 2.2%, max_pos=2 → ~62% pass rate, 17.5% chance within 20 trading days, campaign odds >98% with four evals.
- **Live/Funded Config:** Reduce A-scale to 0.6 and daily cap to 1.8% (≈30% haircut) while keeping risk-budget gating and multi-position logic; still ~20–45% pass rate per sensitivity table with max_pos=1–2, and max daily loss stays below 1.4–2.0%.

## Shadow-Trading FTMO Trials

Before enabling auto-execution, mirror the deployment preset on an FTMO free trial:

1. Install the `MetaTrader5` Python package inside `.venv` and keep MT5 running.
2. Schedule `python scripts/run_live_signals_ftmo.py` every M15 bar.
3. The script logs qualifying trades to `outputs/live_signals_ftmo.csv` (direction, stops, TP, tier, risk fraction).
4. Manually execute matching trades on the FTMO trial to confirm behaviour aligns with the backtests.

See `docs/LIVE_SIGNALS_FTMO.md` for full instructions.
