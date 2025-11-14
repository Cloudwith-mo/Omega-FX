#!/usr/bin/env python3
"""CLI helper to run the Omega FX backtest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - path hack for CLI usage
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

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
        default="data/eurusd_placeholder.csv",
        help="Path to a EUR/USD hourly OHLCV CSV file.",
    )
    parser.add_argument(
        "--starting_equity",
        type=float,
        default=10_000.0,
        help="Initial equity for the backtest.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="outputs",
        help="Directory for equity curve / trade logs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_path = Path(args.data_path)

    if not data_path.exists():
        print(f"[!] Data file not found: {data_path}")
        return 1

    try:
        df = pd.read_csv(data_path)
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"[!] Failed to load CSV: {exc}")
        return 1

    if df.empty:
        print(
            "Loaded zero rows. Please supply historical EUR/USD data "
            "to perform a backtest."
        )
        return 0

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        print(f"[!] CSV missing required columns: {sorted(missing)}")
        return 1

    try:
        result = run_backtest(df, starting_equity=args.starting_equity)
    except ValueError as exc:
        print(f"[!] Backtest aborted: {exc}")
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n===== BACKTEST SUMMARY =====")
    print(f"Starting equity : ${args.starting_equity:,.2f}")
    print(f"Final equity    : ${result.final_equity:,.2f}")
    print(f"Total return    : {result.total_return:.2%}")
    print(f"Max drawdown    : {result.max_drawdown:.2%}")
    print(f"Win rate        : {result.win_rate:.2%}")
    print(f"Number of trades: {result.number_of_trades}")

    equity_path = output_dir / "equity_curve.csv"
    trades_path = output_dir / "trades.csv"
    result.equity_curve.to_csv(equity_path, header=["equity"])
    pd.DataFrame(result.trades).to_csv(trades_path, index=False)
    print(f"Saved equity curve to {equity_path}")
    print(f"Saved trade log to {trades_path}")

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
