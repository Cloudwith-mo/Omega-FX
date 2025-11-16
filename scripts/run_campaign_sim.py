#!/usr/bin/env python3
"""Monte-Carlo campaign simulator using challenge run history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate campaign pass odds from challenge runs.")
    parser.add_argument(
        "--runs_csv",
        type=Path,
        default=Path("results/challenge_runs.csv"),
        help="CSV of challenge runs (produced by run_challenge_sim.py).",
    )
    parser.add_argument(
        "--num_evals",
        type=int,
        nargs="+",
        default=[4, 8, 12],
        help="Evaluation counts to sweep (N in campaign).",
    )
    parser.add_argument(
        "--fees",
        type=float,
        nargs="+",
        default=[325.0, 650.0],
        help="Per-evaluation fee grid.",
    )
    parser.add_argument(
        "--max_trading_days",
        type=int,
        default=None,
        help="Optional filter: only use runs with <= this many trading days.",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=20000,
        help="Monte-Carlo sample count.",
    )
    parser.add_argument(
        "--start_equity",
        type=float,
        default=100_000.0,
        help="Starting equity per evaluation (used for return calculation).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/campaign_stats_m15_full.csv"),
        help="CSV output path.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility.",
    )
    return parser.parse_args()


def load_runs(path: Path, max_days: int | None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Challenge runs CSV not found at {path}")
    df = pd.read_csv(path)
    required = {"passed", "final_equity", "num_trading_days"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Challenge runs missing columns: {sorted(missing)}")
    if max_days is not None:
        df = df[df["num_trading_days"] <= max_days].copy()
    if df.empty:
        raise ValueError("No runs remain after applying filters.")
    return df.reset_index(drop=True)


def simulate_campaigns(
    df: pd.DataFrame,
    num_evals: list[int],
    fees: list[float],
    sims: int,
    start_equity: float,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    passes = df["passed"].astype(bool).to_numpy()
    pnl = df["final_equity"].to_numpy() - start_equity
    trading_days = df["num_trading_days"].to_numpy()
    n_runs = len(df)
    rows: list[dict] = []

    for n in num_evals:
        draw_idx = rng.integers(0, n_runs, size=(sims, n))
        sampled_pass = passes[draw_idx]
        sampled_pnl = pnl[draw_idx]
        sampled_days = trading_days[draw_idx]
        pass_counts = sampled_pass.sum(axis=1)
        first_pass_mask = sampled_pass.cumsum(axis=1) > 0
        first_pass_days = np.where(first_pass_mask, sampled_days, np.nan)
        min_days = np.full(sims, np.nan)
        has_pass_row = pass_counts > 0
        if np.any(has_pass_row):
            min_days[has_pass_row] = np.nanmin(first_pass_days[has_pass_row], axis=1)
        for fee in fees:
            campaign_fee = fee * n
            total_pnl = sampled_pnl.sum(axis=1) - campaign_fee
            at_least_one = pass_counts > 0
            row = {
                "num_evals": n,
                "fee_per_eval": fee,
                "campaign_fee": campaign_fee,
                "pass_prob_at_least_one": float(np.mean(at_least_one)),
                "mean_passes": float(np.mean(pass_counts)),
                "mean_profit": float(np.mean(total_pnl)),
                "median_profit": float(np.median(total_pnl)),
                "p10_profit": float(np.percentile(total_pnl, 10)),
                "p90_profit": float(np.percentile(total_pnl, 90)),
                "mean_trades_per_campaign": None,
            }
            if np.any(at_least_one):
                row["mean_time_to_first_pass"] = float(np.nanmean(min_days[at_least_one]))
            else:
                row["mean_time_to_first_pass"] = None
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    args = parse_args()
    df = load_runs(args.runs_csv, args.max_trading_days)
    table = simulate_campaigns(
        df,
        num_evals=args.num_evals,
        fees=args.fees,
        sims=args.simulations,
        start_equity=args.start_equity,
        seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.output, index=False)
    print(f"Saved campaign stats to {args.output}")
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
