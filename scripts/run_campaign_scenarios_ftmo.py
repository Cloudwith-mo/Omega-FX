#!/usr/bin/env python3
"""Monte-Carlo campaign scenarios for the FTMO deployment preset."""

from __future__ import annotations

import argparse
import ast
import json
import math
from dataclasses import dataclass
from pathlib import Path
import heapq

import numpy as np
import pandas as pd


@dataclass
class EvalSample:
    passed: bool
    duration: float


@dataclass
class FundedSample:
    total_payout: float
    payouts: list[dict]
    account_died: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate FTMO campaign strategies A/B.")
    parser.add_argument(
        "--eval_runs",
        type=Path,
        default=Path("results/ftmo_eval_runs.csv"),
        help="CSV of FTMO eval runs (produced via run_ftmo_eval_sim.py).",
    )
    parser.add_argument(
        "--funded_runs_6m",
        type=Path,
        default=Path("results/funded_payout_ftmo_6m_runs.csv"),
        help="CSV of funded payout simulations for 6 months.",
    )
    parser.add_argument(
        "--funded_runs_12m",
        type=Path,
        default=Path("results/funded_payout_ftmo_12m_runs.csv"),
        help="CSV of funded payout simulations for 12 months.",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=20000,
        help="Monte-Carlo campaigns per scenario.",
    )
    parser.add_argument(
        "--output_prefix",
        type=str,
        default="results/campaign_scenarios_ftmo",
        help="Base path for scenario outputs.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=123,
        help="Random seed for reproducibility.",
    )
    return parser.parse_args()


def load_eval_runs(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Eval runs CSV not found: {path}")
    df = pd.read_csv(path)
    required = {"passed", "num_trading_days"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Eval runs missing columns: {sorted(missing)}")
    df["passed"] = df["passed"].astype(bool)
    df["num_trading_days"] = df["num_trading_days"].astype(float)
    if df.empty:
        raise ValueError("Eval runs CSV is empty.")
    return df.reset_index(drop=True)


def load_funded_runs(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Funded runs CSV not found: {path}")
    df = pd.read_csv(path)
    required = {"total_payout", "account_died", "payouts"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Funded runs missing columns: {sorted(missing)}")
    df["account_died"] = df["account_died"].astype(bool)
    df["parsed_payouts"] = df["payouts"].apply(_parse_payouts)
    if df.empty:
        raise ValueError(f"Funded runs CSV {path} is empty.")
    return df.reset_index(drop=True)


def _parse_payouts(value: object) -> list[dict]:
    if isinstance(value, str) and value.strip():
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            pass
    return []


def sample_eval(eval_df: pd.DataFrame, rng: np.random.Generator) -> EvalSample:
    idx = rng.integers(0, len(eval_df))
    row = eval_df.iloc[idx]
    return EvalSample(passed=bool(row["passed"]), duration=float(row["num_trading_days"]))


def sample_funded(
    funded_df: pd.DataFrame,
    rng: np.random.Generator,
    start_day: float,
    horizon_days: float,
    horizon_months: int,
    day_per_month: float = 21.0,
) -> tuple[float, np.ndarray, bool]:
    if start_day >= horizon_days:
        return 0.0, np.zeros(horizon_months), False
    idx = rng.integers(0, len(funded_df))
    row = funded_df.iloc[idx]
    payouts = row["parsed_payouts"]
    total = 0.0
    monthly = np.zeros(horizon_months)
    for entry in payouts:
        rel_day = float(entry.get("day", 0.0))
        amount = float(entry.get("amount", 0.0))
        abs_day = start_day + rel_day
        if abs_day > horizon_days:
            continue
        total += amount
        month_idx = min(horizon_months - 1, int(abs_day // day_per_month))
        monthly[month_idx] += amount
    return total, monthly, bool(row["account_died"])


def simulate_strategy_a_single(
    eval_df: pd.DataFrame,
    funded_df: pd.DataFrame,
    horizon_days: float,
    horizon_months: int,
    rng: np.random.Generator,
) -> tuple[float, np.ndarray, bool]:
    total = 0.0
    monthly = np.zeros(horizon_months)
    any_death = False
    for _ in range(4):
        sample = sample_eval(eval_df, rng)
        if not sample.passed:
            continue
        finish_day = sample.duration
        funded_total, month_contrib, death = sample_funded(funded_df, rng, finish_day, horizon_days, horizon_months)
        total += funded_total
        monthly += month_contrib
        any_death = any_death or death
    return total, monthly, any_death


def simulate_strategy_b_single(
    eval_df: pd.DataFrame,
    funded_df: pd.DataFrame,
    horizon_days: float,
    horizon_months: int,
    rng: np.random.Generator,
) -> tuple[float, np.ndarray, bool]:
    # Stage 1: eight smaller evals start at t=0
    request_times: list[float] = []
    for _ in range(8):
        sample = sample_eval(eval_df, rng)
        if sample.passed and sample.duration < horizon_days:
            request_times.append(sample.duration)
    request_times.sort()
    total = 0.0
    monthly = np.zeros(horizon_months)
    any_death = False
    active: list[float] = []
    current_time = 0.0
    for ready_time in request_times:
        current_time = max(current_time, ready_time)
        while len(active) >= 4:
            finished = heapq.heappop(active)
            current_time = max(current_time, finished)
        start_time = max(current_time, ready_time)
        big_eval = sample_eval(eval_df, rng)
        finish_time = start_time + big_eval.duration
        heapq.heappush(active, finish_time)
        if big_eval.passed and finish_time < horizon_days:
            funded_total, month_contrib, death = sample_funded(
                funded_df,
                rng,
                finish_time,
                horizon_days,
                horizon_months,
            )
            total += funded_total
            monthly += month_contrib
            any_death = any_death or death
    return total, monthly, any_death


def simulate_campaigns(
    strategy: str,
    eval_df: pd.DataFrame,
    funded_df: pd.DataFrame,
    horizon_months: int,
    sims: int,
    rng: np.random.Generator,
) -> dict:
    horizon_days = horizon_months * 21.0
    totals = np.zeros(sims)
    deaths = np.zeros(sims, dtype=bool)
    monthly = np.zeros((sims, horizon_months))
    for i in range(sims):
        if strategy == "A":
            total, month_contrib, death = simulate_strategy_a_single(eval_df, funded_df, horizon_days, horizon_months, rng)
        elif strategy == "B":
            total, month_contrib, death = simulate_strategy_b_single(eval_df, funded_df, horizon_days, horizon_months, rng)
        else:
            raise ValueError(f"Unknown strategy '{strategy}'")
        totals[i] = total
        monthly[i] = month_contrib
        deaths[i] = death
    cumulative = monthly.cumsum(axis=1)
    summary = {
        "strategy": strategy,
        "horizon_months": horizon_months,
        "simulations": sims,
        "mean_total_payout": float(np.mean(totals)),
        "median_total_payout": float(np.median(totals)),
        "p10_total_payout": float(np.percentile(totals, 10)),
        "p90_total_payout": float(np.percentile(totals, 90)),
        "prob_total_ge_10k": float(np.mean(totals >= 10_000)),
        "prob_total_ge_50k": float(np.mean(totals >= 50_000)),
        "prob_total_ge_100k": float(np.mean(totals >= 100_000)),
        "prob_no_payout": float(np.mean(np.isclose(totals, 0.0))),
        "prob_any_account_death": float(np.mean(deaths)),
        "mean_monthly_payouts": monthly.mean(axis=0).round(2).tolist(),
        "median_monthly_payouts": np.median(monthly, axis=0).round(2).tolist(),
        "mean_cumulative_payouts": cumulative.mean(axis=0).round(2).tolist(),
        "median_cumulative_payouts": np.median(cumulative, axis=0).round(2).tolist(),
    }
    return summary, totals, monthly, cumulative, deaths


def write_outputs(
    summary: dict,
    totals: np.ndarray,
    monthly: np.ndarray,
    cumulative: np.ndarray,
    output_json: Path,
    output_csv: Path,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    df = pd.DataFrame(
        [
            {
                "strategy": summary["strategy"],
                "horizon_months": summary["horizon_months"],
                "mean_total_payout": summary["mean_total_payout"],
                "median_total_payout": summary["median_total_payout"],
                "p10_total_payout": summary["p10_total_payout"],
                "p90_total_payout": summary["p90_total_payout"],
                "prob_total_ge_10k": summary["prob_total_ge_10k"],
                "prob_total_ge_50k": summary["prob_total_ge_50k"],
                "prob_total_ge_100k": summary["prob_total_ge_100k"],
                "prob_no_payout": summary["prob_no_payout"],
                "prob_any_account_death": summary["prob_any_account_death"],
            }
        ]
    )
    df.to_csv(output_csv, index=False)
    print(f"[+] Saved scenario JSON -> {output_json}")
    print(f"[+] Saved scenario CSV  -> {output_csv}")


def main() -> int:
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    eval_df = load_eval_runs(args.eval_runs)
    funded_6m = load_funded_runs(args.funded_runs_6m)
    funded_12m = load_funded_runs(args.funded_runs_12m)
    strategies = ["A", "B"]
    horizon_map = {6: funded_6m, 12: funded_12m}
    for strategy in strategies:
        for horizon_months, funded_df in horizon_map.items():
            summary, totals, monthly, cumulative, deaths = simulate_campaigns(
                strategy,
                eval_df,
                funded_df,
                horizon_months,
                args.simulations,
                rng,
            )
            json_path = Path(f"{args.output_prefix}_{strategy}_{horizon_months}m.json")
            csv_path = Path(f"{args.output_prefix}_{strategy}_{horizon_months}m.csv")
            write_outputs(summary, totals, monthly, cumulative, json_path, csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

