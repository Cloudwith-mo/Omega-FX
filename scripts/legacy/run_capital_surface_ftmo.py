#!/usr/bin/env python3
"""Grid search surface for PLAN_D FTMO capital plans."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.legacy.run_capital_plan_sim import (  # noqa: E402
    load_eval_runs,
    load_funded_runs,
    simulate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a capital-plan surface for FTMO PLAN_D scenarios."
    )
    parser.add_argument("--firm", type=str, default="FTMO_CHALLENGE")
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument(
        "--initial_bankrolls", type=float, nargs="+", default=[2000, 5000, 10000]
    )
    parser.add_argument("--evals_per_wave", type=int, nargs="+", default=[4, 6])
    parser.add_argument("--waves_per_month", type=int, nargs="+", default=[1, 2])
    parser.add_argument(
        "--reinvest_fractions", type=float, nargs="+", default=[0.5, 0.7, 0.9]
    )
    parser.add_argument(
        "--feeder_fee", type=float, default=60.0, help="Feeder eval fee."
    )
    parser.add_argument(
        "--large_fee", type=float, default=350.0, help="Large (100k) eval fee."
    )
    parser.add_argument(
        "--stage2_trigger",
        type=float,
        default=10000.0,
        help="Payout trigger for stage 2.",
    )
    parser.add_argument(
        "--stage1_month_limit",
        type=float,
        default=6.0,
        help="Month index to automatically enter stage 2.",
    )
    parser.add_argument(
        "--large_fraction",
        type=float,
        default=0.5,
        help="Fraction of evals that become large in stage 2.",
    )
    parser.add_argument("--risk_budget_fraction", type=float, default=0.7)
    parser.add_argument(
        "--eval_runs", type=Path, default=Path("results/minimal_ftmo_eval_runs.csv")
    )
    parser.add_argument(
        "--funded_runs",
        type=Path,
        default=Path("results/funded_payout_ftmo_12m_runs.csv"),
    )
    parser.add_argument("--funded_horizon_months", type=int, default=12)
    parser.add_argument("--simulations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/capital_surface_ftmo_plan_d_12m.csv"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    eval_df = load_eval_runs(args.eval_runs)
    funded_df = load_funded_runs(args.funded_runs, args.funded_horizon_months)
    rows: list[dict] = []
    for bankroll in args.initial_bankrolls:
        for epw in args.evals_per_wave:
            for wpm in args.waves_per_month:
                for reinvest in args.reinvest_fractions:
                    cfg = SimpleNamespace(
                        firm=args.firm,
                        months=args.months,
                        evals_per_wave=epw,
                        waves_per_month=wpm,
                        eval_fee=args.feeder_fee,
                        initial_bankroll=bankroll,
                        risk_budget_fraction=args.risk_budget_fraction,
                        reinvest_fraction=reinvest,
                        plan_mode="PLAN_D",
                        feeder_eval_fee=args.feeder_fee,
                        large_eval_fee=args.large_fee,
                        plan_d_stage2_trigger=args.stage2_trigger,
                        plan_d_stage1_month_limit=args.stage1_month_limit,
                        plan_d_large_fraction=args.large_fraction,
                        eval_runs=args.eval_runs,
                        funded_runs=args.funded_runs,
                        funded_horizon_months=args.funded_horizon_months,
                        simulations=args.simulations,
                        seed=args.seed,
                        output=Path("capital_surface_tmp.json"),
                        output_runs=Path("capital_surface_tmp.csv"),
                    )
                    summary, _ = simulate(cfg, eval_df, funded_df)
                    rows.append(
                        {
                            "initial_bankroll": bankroll,
                            "evals_per_wave": epw,
                            "waves_per_month": wpm,
                            "reinvest_fraction": reinvest,
                            "mean_payout": summary["mean_total_payout"],
                            "median_payout": summary["median_total_payout"],
                            "p_total_ge_10k": summary["prob_total_ge_10k"],
                            "p_total_ge_50k": summary["prob_total_ge_50k"],
                            "p_total_ge_100k": summary["prob_total_ge_100k"],
                            "p_net_loss": summary["p_net_loss"],
                            "p_bankroll_breach": summary["prob_any_bankroll_breach"],
                            "mean_time_to_5k": summary["mean_months_to_5k"],
                            "mean_time_to_10k": summary["mean_months_to_10k"],
                            "mean_evals_launched": summary["mean_evals_launched"],
                        }
                    )
    df = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Saved surface results to {args.output}")
    print(df.sort_values("p_total_ge_100k", ascending=False).head())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
