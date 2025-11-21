#!/usr/bin/env python3
"""Normalize MT5-exported H1 CSV files for Omega FX."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


def _normalize_header(name: str) -> str:
    return name.strip().lower().strip("<>").replace(" ", "_")


def _detect_columns(df: pd.DataFrame) -> tuple[str | None, str | None, str | None]:
    cols = {_normalize_header(col): col for col in df.columns}
    time_col = None
    date_col = None

    for key in ("time", "datetime", "timestamp"):
        if key in cols:
            time_col = cols[key]
            break

    for key in ("date", "day"):
        if key in cols:
            date_col = cols[key]
            break

    return time_col, date_col, cols.get("time", time_col)


def _combine_timestamp(
    df: pd.DataFrame, time_col: str | None, date_col: str | None
) -> pd.Series:
    if time_col and date_col:
        combined = (
            df[date_col].astype(str).str.strip()
            + " "
            + df[time_col].astype(str).str.strip()
        )
    elif time_col:
        combined = df[time_col].astype(str).str.strip()
    else:
        raise ValueError("Unable to locate time columns in MT5 export.")
    timestamps = pd.to_datetime(combined, utc=True, errors="coerce")
    return timestamps


def _select_volume_column(df: pd.DataFrame) -> str:
    for key in ("tickvol", "volume", "vol"):
        for col in df.columns:
            if _normalize_header(col) == key:
                return col
    raise ValueError("Unable to locate volume/tick volume column in MT5 export.")


def _infer_timeframe(path: Path, explicit: str | None) -> str:
    if explicit:
        return explicit.upper()
    name = path.stem.upper()
    match = re.search(r"_(H1|M15|H4)", name)
    if match:
        return match.group(1)
    return "H1"


def _normalize_mt5_csv(input_path: Path, symbol: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(input_path, sep=None, engine="python")
    except Exception:
        df = pd.read_csv(input_path)
    if df.empty:
        raise ValueError("MT5 export is empty.")

    time_col, date_col, _ = _detect_columns(df)
    timestamps = _combine_timestamp(df, time_col, date_col)

    for col in (time_col, date_col):
        if col and col not in {"timestamp"}:
            df = df.drop(columns=[col], errors="ignore")

    rename_map = {}
    for col in df.columns:
        key = _normalize_header(col)
        if key in {"open", "high", "low", "close"}:
            rename_map[col] = key
    df = df.rename(columns=rename_map)

    required = {"open", "high", "low", "close"}
    if not required.issubset(df.columns):
        missing = sorted(required - set(df.columns))
        raise ValueError(f"MT5 export missing columns: {missing}")

    volume_col = _select_volume_column(df)
    df = df.rename(columns={volume_col: "volume"})

    df["timestamp"] = timestamps
    df = df.dropna(subset=["timestamp"])

    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=numeric_cols)

    df = df.sort_values("timestamp").drop_duplicates("timestamp")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(
        drop=True
    )

    return df


def _validate_timeframe(
    df: pd.DataFrame, timeframe: str
) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    start = pd.Timestamp(df["timestamp"].iloc[0])
    end = pd.Timestamp(df["timestamp"].iloc[-1])
    timeframe = "unknown"
    if len(df) > 1:
        deltas = df["timestamp"].diff().dropna()
        if not deltas.empty:
            median_delta = deltas.median()
            timeframe = f"{median_delta}".replace("0 days ", "")
    return start, end, timeframe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize MT5 H1 CSV exports.")
    parser.add_argument("--symbol", required=True, help="Symbol name, e.g. EURUSD")
    parser.add_argument(
        "--input", type=Path, required=True, help="Path to the raw MT5 CSV export."
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination for the normalized CSV (e.g. data/EURUSD_H1.csv).",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite the destination if it exists."
    )
    parser.add_argument(
        "--timeframe",
        choices=["H1", "M15", "H4"],
        default=None,
        help="Optional timeframe hint; inferred from filename when omitted.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        print(f"[!] Input file not found: {args.input}")
        return 1
    if args.output.exists() and not args.force:
        print(
            f"[!] Output file already exists: {args.output}. Use --force to overwrite."
        )
        return 1

    timeframe = _infer_timeframe(args.input, args.timeframe)
    try:
        df = _normalize_mt5_csv(args.input, args.symbol.upper())
    except ValueError as exc:
        print(f"[!] Failed to normalize {args.symbol}: {exc}")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)

    start, end, median = _validate_timeframe(df, timeframe)
    print(
        f"{args.symbol.upper()} {timeframe}: {len(df):,} bars saved to {args.output}. "
        f"Range: {start} → {end} | Median step: {median}"
    )
    print(
        f"Note: ensure your MT5 export timeframe matches {timeframe} and timestamps are UTC or adjusted accordingly."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
