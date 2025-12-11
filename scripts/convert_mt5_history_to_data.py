#!/usr/bin/env python3
"""Convert MT5 History Center exports into Omega FX data/<SYMBOL>_<TF>.csv format."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.prepare_mt5_data import _infer_timeframe, _normalize_mt5_csv, _validate_timeframe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize raw MT5 history CSVs to Omega format.")
    parser.add_argument("--symbol", required=True, help="Symbol (e.g., XAUUSD)")
    parser.add_argument(
        "--timeframe",
        choices=["M15", "H1", "H4"],
        required=True,
        help="Timeframe of the raw export (M15/H1/H4).",
    )
    parser.add_argument("--input", type=Path, required=True, help="Raw MT5 CSV path (e.g., mt5_exports/XAUUSD_M15_raw.csv)")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination CSV under data/ (e.g., data/XAUUSD_M15.csv)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite output if it already exists.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbol = args.symbol.upper()
    if not args.input.exists():
        print(f"[!] Input not found: {args.input}")
        return 1
    if args.output.exists() and not args.force:
        print(f"[!] Output exists: {args.output}. Use --force to overwrite.")
        return 1

    try:
        df = _normalize_mt5_csv(args.input, symbol)
    except Exception as exc:
        print(f"[!] Failed to normalize {symbol} {args.timeframe}: {exc}")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)

    start, end, median = _validate_timeframe(df, args.timeframe)
    inferred_tf = _infer_timeframe(args.input, args.timeframe)
    print(
        f"{symbol} {inferred_tf}: {len(df):,} bars saved to {args.output}. "
        f"Range: {start} → {end} | Median step: {median}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
