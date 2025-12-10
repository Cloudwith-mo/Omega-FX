#!/usr/bin/env python3
"""Run FundedNext-style challenge simulations."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.settings import (  # noqa: E402
    ACCOUNT_PHASE_PROFILES,
    DEFAULT_CHALLENGE,
    DEFAULT_CHALLENGE_CONFIG,
    DEFAULT_DATA_PATH,
    DEFAULT_FIRM_PROFILE,
    DEFAULT_TRADING_FIRM,
    FIRM_PROFILES,
    SYMBOLS,
    ChallengeConfig,
    resolve_trading_phase_profile,
)
from core.challenge import ChallengeOutcome, run_challenge_sweep  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate FundedNext challenge outcomes."
    )
    parser.add_argument(
        "--data_path",
        type=str,
        default=str(DEFAULT_DATA_PATH),
        help="Path to EURUSD H1 CSV data.",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=500,
        help="Number of rows to skip between challenge seeds.",
    )
    parser.add_argument(
        "--max_trading_days", type=int, default=None, help="Override max trading days."
    )
    parser.add_argument(
        "--max_calendar_days",
        type=int,
        default=None,
        help="Override max calendar days.",
    )
    parser.add_argument(
        "--min_trading_days", type=int, default=None, help="Override min trading days."
    )
    parser.add_argument(
        "--portfolio",
        action="store_true",
        help="Use all configured symbols (multi-pair portfolio) instead of a single CSV.",
    )
    parser.add_argument(
        "--entry_mode",
        choices=["H1_ONLY", "M15_WITH_H1_CTX", "HYBRID"],
        default=None,
        help="Override entry mode (defaults to config ENTRY_MODE).",
    )
    parser.add_argument(
        "--firm_profile",
        choices=sorted(FIRM_PROFILES.keys()),
        default=None,
        help="Override internal firm profile (TIGHT_PROP, LOOSE_PROP, ...).",
    )
    parser.add_argument(
        "--trading_firm",
        choices=sorted(ACCOUNT_PHASE_PROFILES.keys()),
        default=None,
        help="Trading firm key (ftmo, fundednext, aqua) when using account-phase presets.",
    )
    parser.add_argument(
        "--account_phase",
        choices=["EVAL", "FUNDED"],
        default=None,
        help="Account phase preset. When provided, overrides entry mode and firm profile.",
    )
    parser.add_argument(
        "--start_date",
        type=str,
        default=None,
        help="ISO date (YYYY-MM-DD) to start evaluation window.",
    )
    parser.add_argument(
        "--end_date",
        type=str,
        default=None,
        help="ISO date (YYYY-MM-DD) to end evaluation window.",
    )
    return parser.parse_args()


def _filter_symbol_data(
    symbol_data: dict[str, dict[str, pd.DataFrame]] | None,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, dict[str, pd.DataFrame]] | None:
    if symbol_data is None or (not start_date and not end_date):
        return symbol_data
    start_ts = pd.to_datetime(start_date, utc=True) if start_date else None
    end_ts = pd.to_datetime(end_date, utc=True) if end_date else None
    filtered: dict[str, dict[str, pd.DataFrame]] = {}
    for symbol, frames in symbol_data.items():
        new_frames: dict[str, pd.DataFrame] = {}
        for timeframe, df in frames.items():
            working = df.copy()
            if "timestamp" in working.columns:
                working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
            if start_ts is not None:
                working = working[working["timestamp"] >= start_ts]
            if end_ts is not None:
                working = working[working["timestamp"] <= end_ts]
            if not working.empty:
                new_frames[timeframe] = working.reset_index(drop=True)
        if new_frames:
            filtered[symbol] = new_frames
    return filtered or None


def load_price_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Data file missing required columns: {sorted(missing)}")
    return df.sort_values("timestamp").reset_index(drop=True)


def load_portfolio_data() -> dict[str, dict[str, pd.DataFrame]]:
    data: dict[str, dict[str, pd.DataFrame]] = {}

    def _load_frame(label: str, path_str: str | None) -> pd.DataFrame | None:
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            print(
                f"[!] Portfolio symbol missing {label} file at {path}; skipping frame."
            )
            return None
        return load_price_data(path)

    for cfg in SYMBOLS:
        frames: dict[str, pd.DataFrame] = {}
        h1 = _load_frame("H1", cfg.h1_path)
        if h1 is not None:
            frames["H1"] = h1
        else:
            print(f"[!] Portfolio symbol {cfg.name} missing H1 data; skipping symbol.")
            continue

        m15 = _load_frame("M15", cfg.m15_path)
        if m15 is not None:
            frames["M15"] = m15

        h4 = _load_frame("H4", cfg.h4_path)
        if h4 is not None:
            frames["H4"] = h4

        data[cfg.name] = frames

    if not data:
        raise ValueError("No portfolio data available. Prepare MT5 exports first.")
    return data


def summarize_outcomes(outcomes: list[ChallengeOutcome]) -> dict:
    num_runs = len(outcomes)
    num_passed = sum(1 for o in outcomes if o.passed)
    pass_rate = num_passed / num_runs if num_runs else 0.0
    avg_days_pass = (
        sum(o.num_trading_days for o in outcomes if o.passed) / num_passed
        if num_passed
        else 0.0
    )
    failed = [o for o in outcomes if not o.passed]
    avg_days_fail = (
        sum(o.num_trading_days for o in failed) / len(failed) if failed else 0.0
    )
    max_daily_loss = max(
        (o.max_observed_daily_loss_fraction for o in outcomes), default=0.0
    )
    max_trailing_dd = max((o.max_trailing_dd_fraction for o in outcomes), default=0.0)
    failure_breakdown = Counter(o.failure_reason or "passed" for o in outcomes)

    final_returns = [
        (o.final_equity - o.num_trading_days * 0 + 0) / DEFAULT_CHALLENGE.start_equity
        - 1
        for o in outcomes
    ]
    # Replace above with actual fraction: (final_equity/start -1)
    final_returns = [
        (o.final_equity / DEFAULT_CHALLENGE.start_equity) - 1 for o in outcomes
    ]

    def percentile(data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        series = pd.Series(data)
        return float(series.quantile(pct))

    stats = {
        "mean_return": float(pd.Series(final_returns).mean()) if final_returns else 0.0,
        "median_return": float(pd.Series(final_returns).median())
        if final_returns
        else 0.0,
        "p10_return": percentile(final_returns, 0.10),
        "p25_return": percentile(final_returns, 0.25),
        "p75_return": percentile(final_returns, 0.75),
        "p90_return": percentile(final_returns, 0.90),
    }

    trades_series = (
        pd.Series([o.num_trades for o in outcomes])
        if outcomes
        else pd.Series(dtype=float)
    )
    mean_trades = float(trades_series.mean()) if not trades_series.empty else 0.0
    median_trades = float(trades_series.median()) if not trades_series.empty else 0.0

    symbol_totals: dict[str, int] = {}
    for outcome in outcomes:
        for symbol, count in (outcome.trades_per_symbol or {}).items():
            symbol_totals[symbol] = symbol_totals.get(symbol, 0) + count
    mean_trades_per_symbol = (
        {symbol: total / num_runs for symbol, total in symbol_totals.items()}
        if num_runs
        else {}
    )

    hit_thresholds = {
        ">=5pct": sum(1 for r in final_returns if r >= 0.05) / num_runs
        if num_runs
        else 0.0,
        ">=8pct": sum(1 for r in final_returns if r >= 0.08) / num_runs
        if num_runs
        else 0.0,
        ">=10pct": sum(1 for r in final_returns if r >= 0.10) / num_runs
        if num_runs
        else 0.0,
    }

    return {
        "num_runs": num_runs,
        "num_passed": num_passed,
        "pass_rate": pass_rate,
        "avg_trading_days_pass": avg_days_pass,
        "avg_trading_days_fail": avg_days_fail,
        "max_daily_loss_fraction": max_daily_loss,
        "max_trailing_dd_fraction": max_trailing_dd,
        "failure_breakdown": dict(failure_breakdown),
        "return_stats": stats,
        "mean_trades_per_run": mean_trades,
        "median_trades_per_run": median_trades,
        "mean_trades_per_symbol": mean_trades_per_symbol,
        "threshold_hit_rates": hit_thresholds,
    }


def main() -> int:
    args = parse_args()
    symbol_data = None
    df = None

    phase_profile = None
    if args.account_phase:
        firm_key = (args.trading_firm or DEFAULT_TRADING_FIRM).lower()
        phase_profile = resolve_trading_phase_profile(firm_key, args.account_phase)
    firm_profile_name = (
        phase_profile.firm_profile
        if phase_profile
        else args.firm_profile or DEFAULT_FIRM_PROFILE
    ).upper()
    if firm_profile_name not in FIRM_PROFILES:
        firm_profile_name = DEFAULT_FIRM_PROFILE
    effective_entry_mode = (
        phase_profile.entry_mode if phase_profile else args.entry_mode
    )

    if args.portfolio:
        try:
            symbol_data = load_portfolio_data()
        except ValueError as exc:
            print(f"[!] {exc}")
            return 1
        symbol_data = _filter_symbol_data(symbol_data, args.start_date, args.end_date)
    else:
        data_path = Path(args.data_path)
        if not data_path.exists():
            print(f"[!] Data file not found: {data_path}")
            return 1
        df = load_price_data(data_path)
        if args.start_date:
            start_ts = pd.to_datetime(args.start_date, utc=True)
            df = df[df["timestamp"] >= start_ts]
        if args.end_date:
            end_ts = pd.to_datetime(args.end_date, utc=True)
            df = df[df["timestamp"] <= end_ts]
        df = df.reset_index(drop=True)

    challenge_config: ChallengeConfig = DEFAULT_CHALLENGE_CONFIG
    if (
        args.max_trading_days is not None
        or args.max_calendar_days is not None
        or args.min_trading_days is not None
    ):
        challenge_config = replace(
            challenge_config,
            max_trading_days=args.max_trading_days or challenge_config.max_trading_days,
            max_calendar_days=args.max_calendar_days
            or challenge_config.max_calendar_days,
            min_trading_days=args.min_trading_days or challenge_config.min_trading_days,
        )

    firm_cfg = FIRM_PROFILES[firm_profile_name]
    prop_config = replace(
        DEFAULT_CHALLENGE,
        max_total_loss_fraction=firm_cfg.prop_max_total_loss_fraction,
        max_daily_loss_fraction=firm_cfg.prop_max_daily_loss_fraction,
    )
    challenge_config = replace(
        challenge_config,
        max_total_loss_fraction=firm_cfg.prop_max_total_loss_fraction,
        max_daily_loss_fraction=firm_cfg.prop_max_daily_loss_fraction,
    )

    outcomes = run_challenge_sweep(
        price_data=df,
        symbol_data_map=symbol_data,
        challenge_config=challenge_config,
        prop_config=prop_config,
        step=args.step,
        entry_mode=effective_entry_mode,
        firm_profile=firm_profile_name,
        trading_firm=args.trading_firm or DEFAULT_TRADING_FIRM,
        account_phase=args.account_phase,
    )
    if not outcomes:
        print(
            "[!] No challenge runs produced. Check dataset length or --step parameter."
        )
        return 1

    summary = summarize_outcomes(outcomes)

    if (
        summary["max_daily_loss_fraction"]
        > firm_cfg.internal_max_daily_loss_fraction + 1e-9
    ):
        raise RuntimeError("Challenge sweep observed daily loss above internal cap.")
    if summary["failure_breakdown"].get("prop_violation", 0) > 0:
        print("[!] Warning: Prop violation occurred during simulations.")

    print("===== CHALLENGE SIMULATION =====")
    print(f"Runs: {summary['num_runs']}")
    print(f"Passes: {summary['num_passed']} ({summary['pass_rate']:.2%})")
    print(f"Avg trading days (pass): {summary['avg_trading_days_pass']:.2f}")
    print(f"Avg trading days (fail): {summary['avg_trading_days_fail']:.2f}")
    print(f"Max daily loss fraction: {summary['max_daily_loss_fraction']:.2%}")
    print(f"Max trailing DD fraction: {summary['max_trailing_dd_fraction']:.2%}")
    print(f"Failure breakdown: {summary['failure_breakdown']}")
    print(f"Return stats: {summary['return_stats']}")
    print(
        f"Trades/run (mean/median): {summary['mean_trades_per_run']:.1f} / "
        f"{summary['median_trades_per_run']:.1f}"
    )
    if summary["mean_trades_per_symbol"]:
        print("Mean trades per symbol per run:")
        for symbol, value in summary["mean_trades_per_symbol"].items():
            print(f"  {symbol:<8} -> {value:.2f}")
    print(f"Threshold hit rates (5/8/10%): {summary['threshold_hit_rates']}")

    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)

    runs_path = results_dir / "challenge_runs.csv"
    runs_df = pd.DataFrame(asdict(outcome) for outcome in outcomes)
    runs_df.to_csv(runs_path, index=False)

    summary_path = results_dir / "challenge_summary.json"
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print(f"Saved run details to {runs_path}")
    print(f"Saved summary to {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
