#!/usr/bin/env python3
"""Download H1 FX data from Alpha Vantage and normalize for Omega FX."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

BASE_URL = "https://www.alphavantage.co/query"
SYMBOL_MAP = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
}
DEFAULT_OUTPUT_DIR = Path("data")


def _build_url(symbol: str, api_key: str) -> str:
    from_symbol, to_symbol = SYMBOL_MAP[symbol]
    params = {
        "function": "FX_INTRADAY",
        "from_symbol": from_symbol,
        "to_symbol": to_symbol,
        "interval": "60min",
        "outputsize": "full",
        "datatype": "json",
        "apikey": api_key,
    }
    return f"{BASE_URL}?{urlencode(params)}"


def _fetch_json(url: str) -> dict:
    try:
        with urlopen(url) as resp:
            text = resp.read().decode("utf-8")
    except HTTPError as exc:  # pragma: no cover - network guard
        raise RuntimeError(f"HTTP error {exc.code}: {exc.reason}") from exc
    except URLError as exc:  # pragma: no cover - network guard
        raise RuntimeError(f"Network error: {exc.reason}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Response was not valid JSON.") from exc

    if "Error Message" in data:
        raise RuntimeError(data["Error Message"])
    if "Note" in data:
        raise RuntimeError(data["Note"])
    return data


def _normalize_timeseries(payload: dict, symbol: str) -> pd.DataFrame:
    key = "Time Series FX (60min)"
    if key not in payload:
        raise RuntimeError("Unexpected API response: missing FX time series.")
    series = payload[key]
    rows = []
    for ts, fields in series.items():
        try:
            rows.append(
                {
                    "timestamp": pd.to_datetime(ts, utc=True),
                    "open": float(fields.get("1. open")),
                    "high": float(fields.get("2. high")),
                    "low": float(fields.get("3. low")),
                    "close": float(fields.get("4. close")),
                    "volume": float(fields.get("5. volume", 0.0)),
                }
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Failed parsing row for {symbol} at {ts}: {exc}") from exc

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"No data returned for {symbol}.")

    df = df.dropna().drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def _validate_cadence(df: pd.DataFrame, symbol: str) -> None:
    if len(df) < 2:
        return
    deltas = df["timestamp"].diff().dropna()
    if deltas.empty:
        return
    median_delta = deltas.median()
    if abs(median_delta - pd.Timedelta(hours=1)) > pd.Timedelta(minutes=5):
        print(f"[!] Warning: {symbol} median interval {median_delta} deviates from 1 hour.", file=sys.stderr)
    irregular = deltas[(deltas != pd.Timedelta(hours=1))]
    if not irregular.empty:
        print(f"[!] {symbol} contains {len(irregular)} irregular intervals.", file=sys.stderr)


def _save_dataframe(df: pd.DataFrame, destination: Path, force: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        raise RuntimeError(f"{destination} already exists. Use --force to overwrite.")
    df.to_csv(destination, index=False)


def download_symbol(symbol: str, api_key: str, output_dir: Path, force: bool) -> Path:
    if symbol not in SYMBOL_MAP:
        raise ValueError(f"Unsupported symbol '{symbol}'. Supported: {', '.join(SYMBOL_MAP)}")

    url = _build_url(symbol, api_key)
    payload = _fetch_json(url)
    df = _normalize_timeseries(payload, symbol)
    _validate_cadence(df, symbol)

    destination = output_dir / f"{symbol}_H1.csv"
    _save_dataframe(df, destination, force)

    start = df["timestamp"].iloc[0]
    end = df["timestamp"].iloc[-1]
    print(f"{symbol}: {len(df):,} rows written to {destination} ({start} → {end})")
    return destination


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download FX data from Alpha Vantage.")
    parser.add_argument(
        "--symbol",
        action="append",
        help="Symbol to download (can be repeated). Choices: EURUSD, GBPUSD, USDJPY.",
    )
    parser.add_argument("--all", action="store_true", help="Download all supported symbols.")
    parser.add_argument("--output_dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for normalized CSVs.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not api_key:
        print("[!] ALPHAVANTAGE_API_KEY environment variable is not set.")
        return 1

    symbols: list[str] = []
    if args.all:
        symbols = list(SYMBOL_MAP.keys())
    elif args.symbol:
        symbols = [sym.upper() for sym in args.symbol]
    else:
        print("[!] Specify --symbol SYMBOL (can repeat) or --all.")
        return 1

    exit_code = 0
    for symbol in symbols:
        try:
            download_symbol(symbol, api_key, args.output_dir, args.force)
        except Exception as exc:  # pragma: no cover - network heavy
            print(f"[!] Failed to download {symbol}: {exc}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
