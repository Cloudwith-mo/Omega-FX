#!/usr/bin/env python3
"""Simulate funded account payouts under Omega FX risk controls."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(REPO_ROOT) not in sys.path:  # pragma: no cover - CLI helper
    sys.path.insert(0, str(REPO_ROOT))

from config.settings import (  # noqa: E402
    ACCOUNT_PHASE_PROFILES,
    DEFAULT_CHALLENGE,
    SYMBOLS,
)
from core.backtest import BacktestResult, build_event_stream, run_backtest  # noqa: E402
from core.challenge import _frame_sets_from_map, _slice_symbol_map  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monte-Carlo funded payout simulator.")
    parser.add_argument(
        "--firm",
        choices=sorted(ACCOUNT_PHASE_PROFILES.keys()),
        default="ftmo",
        help="Trading firm profile to use (ftmo, fundednext, aqua).",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=6,
        help="Trading horizon in months (approx 21 trading days per month).",
    )
    parser.add_argument(
        "--num_runs",
        type=int,
        default=100,
        help="Number of Monte-Carlo runs (sliding windows).",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=500,
        help="Event step size between simulation seeds.",
    )
    parser.add_argument(
        "--account_size",
        type=float,
        default=100_000.0,
        help="Nominal account size for the funded profile.",
    )
    parser.add_argument(
        "--payout_split",
        type=float,
        default=0.7,
        help="Fraction of profits withdrawn at each payout event (0-1).",
    )
    parser.add_argument(
        "--payout_interval_days",
        type=int,
        default=20,
        help="Optional scheduled payout interval in trading days (<=0 disables schedule).",
    )
    parser.add_argument(
        "--ratchet_fraction",
        type=float,
        default=0.05,
        help="Profit fraction (relative to protected equity) that triggers an ad-hoc payout.",
    )
    parser.add_argument(
        "--output_prefix",
        type=Path,
        default=Path("results/funded_payout"),
        help="Prefix for CSV/JSON outputs (suffixes added automatically).",
    )
    return parser.parse_args()


def load_portfolio_data() -> dict[str, dict[str, pd.DataFrame]]:
    data: dict[str, dict[str, pd.DataFrame]] = {}
    for cfg in SYMBOLS:
        frames: dict[str, pd.DataFrame] = {}
        for label, path in (("H1", cfg.h1_path), ("M15", cfg.m15_path), ("H4", cfg.h4_path)):
            if not path:
                continue
            csv_path = Path(path)
            if not csv_path.exists():
                continue
            frame = pd.read_csv(csv_path)
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
            frames[label] = frame
        if "H1" not in frames:
            continue
        data[cfg.name] = frames
    if not data:
        raise ValueError("No MT5 data found under data/*.csv. Run prepare_mt5_data.py first.")
    return data


def _simulate_payouts(
    result: BacktestResult,
    *,
    account_size: float,
    payout_split: float,
    payout_interval_days: int,
    ratchet_fraction: float,
) -> dict:
    floor_equity = account_size
    payouts: list[dict] = []
    first_payout_day: int | None = None

    for idx, stat in enumerate(result.daily_stats, start=1):
        day_equity = stat.equity_end_of_day
        gain = day_equity - floor_equity
        if gain <= 0:
            continue
        gain_fraction = gain / floor_equity if floor_equity > 0 else 0.0
        scheduled = payout_interval_days > 0 and idx % payout_interval_days == 0
        threshold_hit = gain_fraction >= ratchet_fraction
        if not (scheduled or threshold_hit):
            continue
        payout_amount = gain * max(0.0, min(1.0, payout_split))
        if payout_amount <= 0:
            continue
        payouts.append({"day": idx, "amount": payout_amount})
        floor_equity += payout_amount
        if first_payout_day is None:
            first_payout_day = idx

    total_payout = sum(p["amount"] for p in payouts)
    largest = max((p["amount"] for p in payouts), default=0.0)

    return {
        "total_payout": total_payout,
        "largest_payout": largest,
        "num_payouts": len(payouts),
        "first_payout_day": first_payout_day,
        "payouts": payouts,
    }


def _summarize(records: list[dict], months: int) -> dict:
    if not records:
        return {}
    totals = [row["total_payout"] for row in records]
    largest = [row["largest_payout"] for row in records]
    alive = sum(1 for row in records if not row["account_died"])
    first_payouts = [row["first_payout_day"] for row in records if row["first_payout_day"] is not None]

    def pct(data: Iterable[float], q: float) -> float:
        if not data:
            return 0.0
        series = pd.Series(list(data))
        return float(series.quantile(q))

    summary = {
        "num_runs": len(records),
        "passive_survival_rate": alive / len(records) if records else 0.0,
        "prob_account_death": 1.0 - (alive / len(records) if records else 0.0),
        "avg_total_payout": statistics.fmean(totals) if totals else 0.0,
        "median_total_payout": statistics.median(totals) if totals else 0.0,
        "p10_total_payout": pct(totals, 0.10),
        "p90_total_payout": pct(totals, 0.90),
        "prob_at_least_one_payout": sum(1 for t in totals if t > 0) / len(records),
        "prob_total_payout_ge_10k": sum(1 for t in totals if t >= 10_000.0) / len(records),
        "prob_total_payout_ge_20k": sum(1 for t in totals if t >= 20_000.0) / len(records),
        "prob_total_payout_ge_50k": sum(1 for t in totals if t >= 50_000.0) / len(records),
        "p_at_least_one_payout_ge_5k": sum(1 for l in largest if l >= 5_000.0) / len(records),
        "mean_time_to_first_payout_days": statistics.fmean(first_payouts) if first_payouts else None,
        "median_time_to_first_payout_days": statistics.median(first_payouts) if first_payouts else None,
        "payout_rate_per_run": statistics.fmean(row["num_payouts"] for row in records) if records else 0.0,
        "max_daily_loss_observed": max(row["max_daily_loss"] for row in records),
        "max_trailing_dd_observed": max(row["max_trailing_dd"] for row in records),
    }
    months = max(1, months)
    summary["mean_monthly_payout"] = summary["avg_total_payout"] / months
    summary["median_monthly_payout"] = summary["median_total_payout"] / months
    return summary


def main() -> int:
    args = parse_args()
    firm_key = args.firm.lower()
    phase = ACCOUNT_PHASE_PROFILES[firm_key]["FUNDED"]

    symbol_data = load_portfolio_data()
    frame_sets = _frame_sets_from_map(symbol_data, phase.entry_mode)
    events = build_event_stream(frame_sets)
    if not events:
        raise RuntimeError("No events available for funded payout simulation.")

    trading_days = max(1, int(math.ceil(args.months * 21)))
    required_tfs = {"M15"} if phase.entry_mode.upper().startswith("M15") else None

    runs: list[dict] = []
    for seed in range(0, len(events), args.step):
        if len(runs) >= args.num_runs:
            break
        start_event = events[seed]
        sliced_map = _slice_symbol_map(
            symbol_data,
            start_event.timestamp,
            trading_days,
            required_timeframes=required_tfs,
        )
        if not sliced_map:
            continue
        challenge_cfg = replace(DEFAULT_CHALLENGE, start_equity=args.account_size)
        try:
            backtest = run_backtest(
                symbol_data_map=sliced_map,
                starting_equity=args.account_size,
                challenge_config=challenge_cfg,
                entry_mode=phase.entry_mode,
                firm_profile=phase.firm_profile,
                trading_firm=firm_key,
                account_phase="FUNDED",
            )
        except ValueError:
            continue

        payouts = _simulate_payouts(
            backtest,
            account_size=args.account_size,
            payout_split=args.payout_split,
            payout_interval_days=args.payout_interval_days,
            ratchet_fraction=args.ratchet_fraction,
        )
        runs.append(
            {
                "run_id": len(runs) + 1,
                "total_payout": payouts["total_payout"],
                "largest_payout": payouts["largest_payout"],
                "num_payouts": payouts["num_payouts"],
                "first_payout_day": payouts["first_payout_day"],
                "account_died": backtest.internal_stop_out_triggered or backtest.prop_fail_triggered,
                "max_daily_loss": backtest.max_daily_loss_fraction,
                "max_trailing_dd": backtest.max_drawdown,
                "payouts": payouts["payouts"],
            }
        )

    if not runs:
        raise RuntimeError("Unable to produce funded payout simulations. Check data horizon or step size.")

    summary = _summarize(runs, args.months)
    output_prefix = args.output_prefix
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_prefix.with_name(f"{output_prefix.stem}_{firm_key}_{args.months}m_runs.csv")
    json_path = output_prefix.with_name(f"{output_prefix.stem}_{firm_key}_{args.months}m_summary.json")

    pd.DataFrame(runs).to_csv(csv_path, index=False)
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "firm": firm_key,
                "months": args.months,
                "account_size": args.account_size,
                "payout_split": args.payout_split,
                "payout_interval_days": args.payout_interval_days,
                "ratchet_fraction": args.ratchet_fraction,
                "summary": summary,
            },
            fh,
            indent=2,
        )

    print("===== FUNDED PAYOUT SIM =====")
    print(f"Firm profile      : {firm_key} (FUNDED)")
    print(f"Runs              : {summary.get('num_runs', 0)}")
    print(f"Avg total payout  : ${summary.get('avg_total_payout', 0.0):,.2f}")
    print(f"Median total payout: ${summary.get('median_total_payout', 0.0):,.2f}")
    print(f"P(>=1 payout)     : {summary.get('prob_at_least_one_payout', 0.0):.2%}")
    print(f"P(account death)  : {summary.get('prob_account_death', 0.0):.2%}")
    if summary.get("mean_time_to_first_payout"):
        print(f"Mean days to first payout: {summary['mean_time_to_first_payout']:.1f}")
    print(f"Saved run details to {csv_path}")
    print(f"Saved summary to   {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
