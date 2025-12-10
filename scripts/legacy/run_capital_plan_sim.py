#!/usr/bin/env python3
"""Simulate multi-wave capital plans using existing FTMO eval and funded distributions."""

from __future__ import annotations

import argparse
import ast
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a capital plan Monte-Carlo simulation."
    )
    parser.add_argument(
        "--firm",
        type=str,
        default="FTMO_CHALLENGE",
        help="Firm profile label (for metadata only).",
    )
    parser.add_argument(
        "--months", type=int, default=12, help="Campaign horizon in months."
    )
    parser.add_argument(
        "--evals_per_wave",
        type=int,
        default=4,
        help="Number of evals launched in each wave.",
    )
    parser.add_argument(
        "--waves_per_month",
        type=int,
        default=1,
        help="How many eval waves start per calendar month.",
    )
    parser.add_argument(
        "--eval_fee",
        type=float,
        default=300.0,
        help="Baseline eval cost (used when plan_mode=BASIC).",
    )
    parser.add_argument(
        "--initial_bankroll",
        type=float,
        default=1000.0,
        help="Starting bankroll allocated to eval fees.",
    )
    parser.add_argument(
        "--risk_budget_fraction",
        type=float,
        default=1.0,
        help="Fraction of current bankroll available for the next eval wave (0-1).",
    )
    parser.add_argument(
        "--reinvest_fraction",
        type=float,
        default=0.2,
        help="Fraction of every payout recycled into bankroll (0.0–1.0).",
    )
    parser.add_argument(
        "--plan_mode",
        choices=["BASIC", "PLAN_D"],
        default="BASIC",
        help="BASIC = legacy behavior, PLAN_D adds feeder→100k staging.",
    )
    parser.add_argument(
        "--feeder_eval_fee",
        type=float,
        default=None,
        help="Eval fee for feeder accounts (defaults to eval_fee).",
    )
    parser.add_argument(
        "--large_eval_fee",
        type=float,
        default=350.0,
        help="Eval fee for large (100k) accounts in PLAN_D stage 2.",
    )
    parser.add_argument(
        "--plan_d_stage2_trigger",
        type=float,
        default=10000.0,
        help="Withdrawn payout threshold that unlocks PLAN_D stage 2.",
    )
    parser.add_argument(
        "--plan_d_stage1_month_limit",
        type=float,
        default=6.0,
        help="Month index (0-based) after which PLAN_D stage 2 activates regardless of payouts.",
    )
    parser.add_argument(
        "--plan_d_large_fraction",
        type=float,
        default=0.5,
        help="Fraction of evals per wave that become large accounts once PLAN_D stage 2 is active.",
    )
    parser.add_argument(
        "--eval_runs",
        type=Path,
        default=Path("results/ftmo_eval_runs.csv"),
        help="CSV of eval runs (produced by run_minimal_ftmo_eval.py).",
    )
    parser.add_argument(
        "--funded_runs",
        type=Path,
        default=Path("results/funded_payout_ftmo_12m_runs.csv"),
        help="CSV of funded payout simulations (6m or 12m horizon).",
    )
    parser.add_argument(
        "--funded_horizon_months",
        type=int,
        default=12,
        help="Months covered by the funded payout CSV (6 or 12).",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=20000,
        help="Number of Monte-Carlo campaigns.",
    )
    parser.add_argument("--seed", type=int, default=2024, help="Random seed.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/capital_plan_ftmo.json"),
        help="Path for the JSON output summary.",
    )
    parser.add_argument(
        "--output_runs",
        type=Path,
        default=Path("results/capital_plan_ftmo_runs.csv"),
        help="Path for the per-simulation CSV output.",
    )
    return parser.parse_args()


def load_eval_runs(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Eval runs CSV not found at {path}")
    df = pd.read_csv(path)
    required = {"passed", "num_trading_days"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Eval runs missing columns: {sorted(missing)}")
    df["passed"] = df["passed"].astype(bool)
    df["num_trading_days"] = df["num_trading_days"].astype(float)
    if df.empty:
        raise ValueError("Eval CSV is empty.")
    return df.reset_index(drop=True)


def load_funded_runs(path: Path, horizon_months: int) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Funded payout CSV not found at {path}")
    df = pd.read_csv(path)
    required = {"payouts"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Funded payout runs missing columns: {sorted(missing)}")
    df["parsed_payouts"] = df["payouts"].apply(_parse_payouts)
    df["monthly_series"] = df["parsed_payouts"].apply(
        lambda entries: _payouts_to_monthly(entries, horizon_months)
    )
    if df.empty:
        raise ValueError("Funded payout CSV is empty.")
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


def _payouts_to_monthly(entries: list[dict], horizon_months: int) -> list[float]:
    arr = [0.0] * horizon_months
    for entry in entries:
        try:
            day = float(entry.get("day", 0.0))
            amount = float(entry.get("amount", 0.0))
        except (TypeError, ValueError):
            continue
        month_idx = int(day // 21.0)
        if 0 <= month_idx < horizon_months:
            arr[month_idx] += amount
    return arr


def sample_eval(eval_df: pd.DataFrame, rng: np.random.Generator) -> tuple[bool, float]:
    idx = rng.integers(0, len(eval_df))
    row = eval_df.iloc[idx]
    return bool(row["passed"]), float(row["num_trading_days"])


def sample_funded_monthly(
    funded_df: pd.DataFrame, rng: np.random.Generator
) -> list[float]:
    idx = rng.integers(0, len(funded_df))
    row = funded_df.iloc[idx]
    return list(row["monthly_series"])


def simulate(
    args: argparse.Namespace, eval_df: pd.DataFrame, funded_df: pd.DataFrame
) -> dict:
    rng = np.random.default_rng(args.seed)
    horizon_months = args.months
    waves = int(args.months * args.waves_per_month)
    time_per_wave = 1.0 / args.waves_per_month
    bankroll_floor = 0.0
    total_payouts = np.zeros(args.simulations)
    bankroll_death = np.zeros(args.simulations, dtype=bool)
    first_5k = np.full(args.simulations, np.nan)
    first_10k = np.full(args.simulations, np.nan)
    final_bankrolls = np.zeros(args.simulations)
    eval_counts = np.zeros(args.simulations)
    feeder_fee = (
        args.feeder_eval_fee if args.feeder_eval_fee is not None else args.eval_fee
    )

    for sim in range(args.simulations):
        bankroll = args.initial_bankroll
        withdrawn_total = 0.0
        monthly_withdrawn = np.zeros(horizon_months)
        monthly_reinvest = np.zeros(horizon_months)
        death = False
        stage2_active = False

        evals_launched = 0
        for wave in range(waves):
            wave_time = wave * time_per_wave
            if wave_time >= args.months:
                break
            wave_month_idx = int(math.floor(wave_time))
            if wave_month_idx >= horizon_months:
                break
            if args.plan_mode == "PLAN_D":
                if not stage2_active:
                    if (
                        withdrawn_total >= args.plan_d_stage2_trigger
                        or wave_time >= args.plan_d_stage1_month_limit
                    ):
                        stage2_active = True
                large_fraction = args.plan_d_large_fraction if stage2_active else 0.0
                large_count = int(round(args.evals_per_wave * large_fraction))
                large_count = max(0, min(large_count, args.evals_per_wave))
                feeder_count = args.evals_per_wave - large_count
                if feeder_count < 0:
                    feeder_count = 0
                if feeder_count + large_count == 0:
                    feeder_count = args.evals_per_wave
                    large_count = 0
                wave_cost = (
                    feeder_count * feeder_fee
                    + large_count * args.large_eval_fee
                )
            else:
                feeder_count = args.evals_per_wave
                large_count = 0
                wave_cost = feeder_count * args.eval_fee
            risk_budget = args.risk_budget_fraction * bankroll
            if wave_cost > risk_budget or wave_cost > bankroll:
                death = True
                break
            bankroll -= wave_cost
            evals_launched += feeder_count + large_count

            def process_eval() -> None:
                passed, duration_days = sample_eval(eval_df, rng)
                finish_time = wave_time + (duration_days / 21.0)
                if not passed or finish_time >= args.months:
                    return
                funded_monthly = sample_funded_monthly(funded_df, rng)
                for offset, amount in enumerate(funded_monthly):
                    if amount <= 0:
                        continue
                    event_month = int(math.floor(finish_time + offset))
                    if event_month >= horizon_months:
                        break
                    withdraw = amount * (1.0 - args.reinvest_fraction)
                    reinvest = amount * args.reinvest_fraction
                    monthly_withdrawn[event_month] += withdraw
                    monthly_reinvest[event_month] += reinvest

            for _ in range(feeder_count):
                process_eval()
            for _ in range(large_count):
                process_eval()

        for month_idx in range(horizon_months):
            withdrawn_total += monthly_withdrawn[month_idx]
            if withdrawn_total >= 5000 and np.isnan(first_5k[sim]):
                first_5k[sim] = month_idx + 1
            if withdrawn_total >= 10000 and np.isnan(first_10k[sim]):
                first_10k[sim] = month_idx + 1
            bankroll += monthly_reinvest[month_idx]
            if bankroll < bankroll_floor:
                death = True

        total_payouts[sim] = withdrawn_total
        bankroll_death[sim] = death
        eval_counts[sim] = evals_launched
        final_bankrolls[sim] = bankroll

    summary = {
        "firm": args.firm,
        "months": args.months,
        "evals_per_wave": args.evals_per_wave,
        "waves_per_month": args.waves_per_month,
        "eval_fee": args.eval_fee,
        "initial_bankroll": args.initial_bankroll,
        "risk_budget_fraction": args.risk_budget_fraction,
        "reinvest_fraction": args.reinvest_fraction,
        "simulations": args.simulations,
        "mean_total_payout": float(np.mean(total_payouts)),
        "median_total_payout": float(np.median(total_payouts)),
        "p10_total_payout": float(np.percentile(total_payouts, 10)),
        "p90_total_payout": float(np.percentile(total_payouts, 90)),
        "prob_total_ge_10k": float(np.mean(total_payouts >= 10_000)),
        "prob_total_ge_25k": float(np.mean(total_payouts >= 25_000)),
        "prob_total_ge_50k": float(np.mean(total_payouts >= 50_000)),
        "prob_total_ge_100k": float(np.mean(total_payouts >= 100_000)),
        "prob_any_bankroll_breach": float(np.mean(bankroll_death)),
        "p_net_loss": float(np.mean(total_payouts < args.initial_bankroll)),
        "mean_final_bankroll": float(np.mean(final_bankrolls)),
        "median_final_bankroll": float(np.median(final_bankrolls)),
        "mean_evals_launched": float(np.mean(eval_counts)),
        "median_evals_launched": float(np.median(eval_counts)),
        "mean_months_to_5k": _nan_mean(first_5k),
        "median_months_to_5k": _nan_median(first_5k),
        "mean_months_to_10k": _nan_mean(first_10k),
        "median_months_to_10k": _nan_median(first_10k),
    }
    per_run = pd.DataFrame(
        {
            "total_payout": total_payouts,
            "final_bankroll": final_bankrolls,
            "evals_launched": eval_counts,
            "bankroll_breach": bankroll_death,
            "months_to_5k": first_5k,
            "months_to_10k": first_10k,
        }
    )
    return summary, per_run


def _nan_median(arr: np.ndarray) -> float | None:
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return None
    return float(np.median(valid))


def _nan_mean(arr: np.ndarray) -> float | None:
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return None
    return float(np.mean(valid))


def main() -> int:
    args = parse_args()
    if not (0.0 <= args.reinvest_fraction <= 1.0):
        raise ValueError("reinvest_fraction must be between 0 and 1.")
    if not (0.0 <= args.risk_budget_fraction <= 1.0):
        raise ValueError("risk_budget_fraction must be between 0 and 1.")
    if not (0.0 <= args.reinvest_fraction <= 1.0):
        raise ValueError("reinvest_fraction must be between 0 and 1.")
    if args.plan_mode == "PLAN_D" and not (
        0.0 <= args.plan_d_large_fraction <= 1.0
    ):
        raise ValueError("plan_d_large_fraction must be between 0 and 1.")
    eval_df = load_eval_runs(args.eval_runs)
    funded_df = load_funded_runs(
        args.funded_runs, args.funded_horizon_months
    )
    summary, per_run = simulate(args, eval_df, funded_df)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2))
    args.output_runs.parent.mkdir(parents=True, exist_ok=True)
    per_run.to_csv(args.output_runs, index=False)
    print(f"Saved capital plan summary to {args.output}")
    print(json.dumps(summary, indent=2))
    print(f"Saved per-run stats to {args.output_runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
