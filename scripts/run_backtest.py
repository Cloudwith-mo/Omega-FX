#!/usr/bin/env python3
"""CLI helper to run the Omega FX backtest."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - path hack for CLI usage
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from config.settings import ACCOUNT_PHASE_PROFILES, DEFAULT_DATA_PATH, DEFAULT_TRADING_FIRM, FIRM_PROFILES
from core.backtest import REQUIRED_COLUMNS, run_backtest

try:  # pragma: no cover
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Omega FX backtest.")
    parser.add_argument(
        "--data_path",
        type=str,
        default=None,
        help=(
            "Path to a EUR/USD hourly OHLCV CSV file (timestamp, open, high, low, close, volume). "
            "Defaults to config DEFAULT_DATA_PATH if omitted."
        ),
    )
    parser.add_argument(
        "--starting_equity",
        type=float,
        default=100_000.0,
        help="Initial equity for the backtest.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="outputs",
        help="Directory for equity curve / trade logs.",
    )
    parser.add_argument(
        "--portfolio",
        action="store_true",
        help="Use all configured symbols instead of a single CSV.",
    )
    parser.add_argument(
        "--entry_mode",
        choices=["H1_ONLY", "M15_WITH_H1_CTX", "HYBRID"],
        default=None,
        help="Override entry mode (default from config).",
    )
    parser.add_argument(
        "--firm_profile",
        choices=sorted(FIRM_PROFILES.keys()),
        default=None,
        help="Override firm profile (internal risk caps).",
    )
    parser.add_argument(
        "--trading_firm",
        choices=sorted(ACCOUNT_PHASE_PROFILES.keys()),
        default=None,
        help="Name of trading firm to use when selecting account-phase presets.",
    )
    parser.add_argument(
        "--account_phase",
        choices=["EVAL", "FUNDED"],
        default=None,
        help="Optional account phase preset. When set, overrides entry mode, tier scales, and firm profile.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbol_data = None
    df = None
    data_source: str | None = None

    if args.portfolio:
        pass
    else:
        data_path = Path(args.data_path or DEFAULT_DATA_PATH)
        if not data_path.exists():
            print(f"[!] Data file not found: {data_path}")
            return 1
        try:
            df = pd.read_csv(data_path)
        except Exception as exc:  # pragma: no cover - CLI guard
            print(f"[!] Failed to load CSV: {exc}")
            return 1
        data_source = str(data_path)
    try:
        result = run_backtest(
            df,
            starting_equity=args.starting_equity,
            data_source=data_source,
            symbol_data_map=symbol_data,
            entry_mode=args.entry_mode,
            firm_profile=args.firm_profile,
            trading_firm=args.trading_firm or DEFAULT_TRADING_FIRM,
            account_phase=args.account_phase,
        )
    except ValueError as exc:
        print(f"[!] Backtest aborted: {exc}")
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trading_days = max(1, len(result.daily_stats))
    trades_per_year = result.number_of_trades / max(1, trading_days / 252)

    combo_summary = {str(combo): count for combo, count in result.pre_risk_combo_counts.items()}

    metrics = {
        "starting_equity": args.starting_equity,
        "final_equity": result.final_equity,
        "total_return_pct": result.total_return * 100,
        "max_drawdown_pct": result.max_drawdown * 100,
        "win_rate_pct": result.win_rate * 100,
        "number_of_trades": result.number_of_trades,
        "average_rr": result.average_rr,
        "risk_mode": result.risk_mode.value,
        "max_daily_loss_fraction": result.max_daily_loss_fraction,
        "internal_stop_out_triggered": result.internal_stop_out_triggered,
        "prop_fail_triggered": result.prop_fail_triggered,
        "mode_transition_summary": result.mode_transition_summary,
        "filtered_counts": result.filtered_trades_by_reason,
        "raw_signal_count": result.raw_signal_count,
        "after_session_count": result.after_session_count,
        "after_trend_count": result.after_trend_count,
        "after_volatility_count": result.after_volatility_count,
        "after_risk_count": result.after_risk_aggression_count,
        "after_breakout_count": result.after_breakout_count,
        "signal_variant_counts": result.signal_variant_counts,
        "trades_per_year": trades_per_year,
        "pre_risk_combo_counts": combo_summary,
        "tier_counts": result.tier_counts,
        "tier_expectancy": result.tier_expectancy,
        "tier_trades_per_year": result.tier_trades_per_year,
        "trades_per_symbol": result.trades_per_symbol,
        "open_position_histogram": result.open_position_histogram,
    }

    print("\n===== BACKTEST SUMMARY =====")
    print(f"Starting equity : ${metrics['starting_equity']:,.2f}")
    print(f"Final equity    : ${metrics['final_equity']:,.2f}")
    print(f"Total return    : {metrics['total_return_pct']:.2f}%")
    print(f"Max drawdown    : {metrics['max_drawdown_pct']:.2f}%")
    print(f"Win rate        : {metrics['win_rate_pct']:.2f}%")
    print(f"Number of trades: {metrics['number_of_trades']}")
    print(f"Average R:R     : {metrics['average_rr']:.2f}x")
    print(f"Trades per year : {metrics['trades_per_year']:.1f}")
    print(f"Max daily loss  : {metrics['max_daily_loss_fraction']:.2%}")
    print(f"Final risk mode : {metrics['risk_mode']}")
    print(f"Internal stop?  : {metrics['internal_stop_out_triggered']}")
    print(f"Prop fail?      : {metrics['prop_fail_triggered']}")
    print(
        "Filtered trades : "
        f"session={metrics['filtered_counts'].get('session', 0)}, "
        f"trend={metrics['filtered_counts'].get('trend', 0)}, "
        f"low_vol={metrics['filtered_counts'].get('low_volatility', 0)}, "
        f"high_vol_sideways={metrics['filtered_counts'].get('high_vol_sideways', 0)}, "
        f"risk_aggr={metrics['filtered_counts'].get('risk_aggression', 0)}, "
        f"max_pos={metrics['filtered_counts'].get('max_open_positions', 0)}"
    )
    print(
        "Signal funnel    : "
        f"raw={metrics['raw_signal_count']} -> "
        f"session={metrics['after_session_count']} -> "
        f"trend={metrics['after_trend_count']} -> "
        f"vol={metrics['after_volatility_count']} -> "
        f"risk={metrics['after_risk_count']} -> "
        f"final={metrics['after_breakout_count']}"
    )
    print(f"Signal variants  : {metrics['signal_variant_counts']}")
    tier_counts = metrics["tier_counts"]
    tier_expectancy = metrics["tier_expectancy"]
    tier_trades_year = metrics["tier_trades_per_year"]
    print("Risk tiers       :")
    for tier in ["A", "B", "UNKNOWN", "C"]:
        trades_tier = tier_counts.get(tier, 0)
        expectancy = tier_expectancy.get(tier, 0.0)
        trades_py = tier_trades_year.get(tier, 0.0)
        print(f"  {tier:<8} trades={trades_tier:4d} | expectancy={expectancy:.2f}R | trades/yr={trades_py:.1f}")
    if metrics["trades_per_symbol"]:
        print("Trades per symbol:")
        for symbol, count in metrics["trades_per_symbol"].items():
            print(f"  {symbol:<8} -> {count}")
    if metrics["open_position_histogram"]:
        print("Open position histogram:")
        for count, occurrences in sorted(metrics["open_position_histogram"].items()):
            print(f"  {count} positions -> {occurrences}")
    pre_risk = result.pre_risk_combo_counts
    top_combos = sorted(pre_risk.items(), key=lambda kv: kv[1], reverse=True)[:5]
    if top_combos:
        print("Top risk combos  :")
        for combo, count in top_combos:
            print(f"  {combo} -> {count}")

    equity_path = output_dir / "equity_curve.csv"
    trades_path = output_dir / "trades.csv"
    result.equity_curve.to_csv(equity_path, header=["equity"])
    pd.DataFrame(result.trades).to_csv(trades_path, index=False)
    print(f"Saved equity curve to {equity_path}")
    print(f"Saved trade log to {trades_path}")

    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    metrics_path = results_dir / f"omega_fx_backtest_{timestamp}.json"
    with metrics_path.open("w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    print(f"Saved metrics summary to {metrics_path}")

    if plt is not None:
        plt.figure(figsize=(11, 5))
        plt.plot(result.equity_curve.index, result.equity_curve.values)
        plt.title("Omega FX Equity Curve")
        plt.xlabel("Timestamp")
        plt.ylabel("Equity ($)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        curve_img = output_dir / "equity_curve.png"
        plt.savefig(curve_img, dpi=200)
        print(f"Saved equity curve plot to {curve_img}")
    else:
        print("matplotlib not available; skipping equity curve plot.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
