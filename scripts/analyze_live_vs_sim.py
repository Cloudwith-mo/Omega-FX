#!/usr/bin/env python3
"""Compare FTMO trial results vs the Omega FX simulation distribution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze live MT5 trades vs simulated eval runs."
    )
    parser.add_argument(
        "--live_trades_csv",
        type=Path,
        required=True,
        help="MT5 export CSV (detailed report).",
    )
    parser.add_argument(
        "--sim_runs_csv",
        type=Path,
        default=Path("results/minimal_ftmo_eval_runs.csv"),
        help="Challenge simulation runs for the matching preset.",
    )
    parser.add_argument(
        "--account_size",
        type=float,
        default=100_000.0,
        help="Starting equity for the live trial (defaults to 100k FTMO).",
    )
    parser.add_argument(
        "--reference_risk_per_trade",
        type=float,
        default=1_000.0,
        help="Reference risk used to convert profit into R multiples (default 1%% of a 100k account).",
    )
    parser.add_argument(
        "--output_json",
        type=Path,
        default=Path("results/live_vs_sim_summary.json"),
        help="Destination for the JSON summary.",
    )
    parser.add_argument(
        "--output_report",
        type=Path,
        default=None,
        help="Optional markdown/text file for a human-readable recap.",
    )
    return parser.parse_args()


def load_live_trades(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Live trades CSV not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("Live trades CSV is empty.")
    timestamp_col = next(
        (col for col in df.columns if col.lower() in {"time", "timestamp", "date"}),
        None,
    )
    if timestamp_col is None:
        raise ValueError(
            "Live trades CSV must include a timestamp column (Time/Timestamp/Date)."
        )
    df["timestamp"] = pd.to_datetime(df[timestamp_col])
    profit = _coalesce_columns(df, ["Profit", "profit"])
    swap = _coalesce_columns(df, ["Swap", "swap"], default=0.0)
    commission = _coalesce_columns(df, ["Commission", "commission"], default=0.0)
    df["pnl"] = profit + swap + commission
    type_col = next((col for col in df.columns if col.lower() == "type"), None)
    if type_col:
        df["direction"] = df[type_col].str.lower()
    else:
        df["direction"] = ""
    return df.sort_values("timestamp").reset_index(drop=True)


def _coalesce_columns(
    df: pd.DataFrame, candidates: list[str], default: float = 0.0
) -> pd.Series:
    for col in candidates:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return pd.Series(default, index=df.index, dtype=float)


def compute_live_metrics(
    df: pd.DataFrame, account_size: float, reference_risk: float
) -> dict:
    cum_pnl = df["pnl"].cumsum()
    equity = account_size + cum_pnl
    total_return_pct = (
        0.0
        if equity.empty
        else ((equity.iloc[-1] - account_size) / account_size) * 100.0
    )
    max_dd_pct = _max_drawdown_pct(equity, account_size)
    max_daily_loss_pct = _max_daily_loss_pct(df, account_size)
    num_trades = int(len(df))
    wins = int((df["pnl"] > 0).sum())
    hit_rate = 0.0 if num_trades == 0 else wins / num_trades
    avg_r = (
        0.0
        if num_trades == 0 or reference_risk <= 0
        else float((df["pnl"] / reference_risk).mean())
    )
    trades_per_day = _trades_per_day(df)
    return {
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_dd_pct,
        "max_daily_loss_pct": max_daily_loss_pct,
        "num_trades": num_trades,
        "hit_rate": hit_rate,
        "avg_r_multiple": avg_r,
        "trades_per_day": trades_per_day,
    }


def _trades_per_day(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    days = df["timestamp"].dt.normalize().nunique()
    if days == 0:
        return float(len(df))
    return len(df) / days


def _max_drawdown_pct(equity_series: pd.Series, starting_equity: float) -> float:
    if equity_series.empty:
        return 0.0
    peak = starting_equity
    max_dd = 0.0
    for value in equity_series:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0.0
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd * 100.0


def _max_daily_loss_pct(df: pd.DataFrame, starting_equity: float) -> float:
    if df.empty:
        return 0.0
    equity = starting_equity
    worst = 0.0
    for day, group in df.groupby(df["timestamp"].dt.date, sort=True):
        start_eq = equity
        pnl = group["pnl"].sum()
        equity = start_eq + pnl
        if pnl < 0 and start_eq > 0:
            loss_pct = abs(pnl / start_eq) * 100.0
            worst = max(worst, loss_pct)
    return worst


def load_sim_runs(path: Path, account_size: float) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Simulation CSV not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("Simulation CSV is empty.")
    final_equity = pd.to_numeric(df["final_equity"], errors="coerce")
    sim_return_pct = (final_equity - account_size) / account_size * 100.0
    max_dd = (
        _coalesce_sim_fraction(
            df, ["max_trailing_dd_fraction", "max_drawdown_fraction"]
        )
        * 100.0
    )
    max_daily = (
        _coalesce_sim_fraction(
            df, ["max_observed_daily_loss_fraction", "max_daily_loss_fraction"]
        )
        * 100.0
    )
    return {
        "return_pct": sim_return_pct.to_numpy(),
        "max_dd_pct": max_dd.to_numpy(),
        "max_daily_loss_pct": max_daily.to_numpy(),
    }


def _coalesce_sim_fraction(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    for col in cols:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    raise ValueError(f"Simulation CSV missing required columns: {cols}")


def percentile_rank(series: np.ndarray, value: float) -> float:
    if series.size == 0:
        return float("nan")
    sorted_series = np.sort(series)
    idx = np.searchsorted(sorted_series, value, side="right")
    return (idx / len(sorted_series)) * 100.0


def build_comparison(live: dict, sim: dict) -> dict:
    return {
        "return_percentile": percentile_rank(
            sim["return_pct"], live["total_return_pct"]
        ),
        "max_drawdown_percentile": percentile_rank(
            sim["max_dd_pct"], live["max_drawdown_pct"]
        ),
        "max_daily_loss_percentile": percentile_rank(
            sim["max_daily_loss_pct"], live["max_daily_loss_pct"]
        ),
        "sim_return_mean_pct": float(np.mean(sim["return_pct"])),
        "sim_return_median_pct": float(np.median(sim["return_pct"])),
        "sim_max_dd_mean_pct": float(np.mean(sim["max_dd_pct"])),
        "sim_max_daily_loss_mean_pct": float(np.mean(sim["max_daily_loss_pct"])),
    }


def render_report(live: dict, comparison: dict) -> str:
    lines = [
        "# Live vs Sim Summary",
        "",
        f"- Live total return: {live['total_return_pct']:.2f}% "
        f"(sim median {comparison['sim_return_median_pct']:.2f}%, percentile {comparison['return_percentile']:.1f})",
        f"- Live max trailing DD: {live['max_drawdown_pct']:.2f}% "
        f"(percentile {comparison['max_drawdown_percentile']:.1f})",
        f"- Live max daily loss: {live['max_daily_loss_pct']:.2f}% "
        f"(percentile {comparison['max_daily_loss_percentile']:.1f})",
        f"- Trades: {live['num_trades']} | Hit rate: {live['hit_rate'] * 100:.1f}% | Avg R: {live['avg_r_multiple']:.2f}",
        "",
        "Flag any percentile above ~80 for drawdowns or below ~20 for returns—those warrant deeper investigation before paying for evals.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    live_df = load_live_trades(args.live_trades_csv)
    live_metrics = compute_live_metrics(
        live_df, args.account_size, args.reference_risk_per_trade
    )
    sim_metrics = load_sim_runs(args.sim_runs_csv, args.account_size)
    comparison = build_comparison(live_metrics, sim_metrics)
    summary = {
        "live_metrics": live_metrics,
        "comparison": comparison,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2))
    if args.output_report:
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text(render_report(live_metrics, comparison))
    print(f"Saved analyzer summary to {args.output_json}")
    if args.output_report:
        print(f"Saved analyzer report to {args.output_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
