#!/usr/bin/env python3
"""Download FX aggregates from the Massive API and emit Omega-style CSVs."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api.massive.com/v2/aggs/ticker"
DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")
AGG_LIMIT = 5000
TIMEFRAME_MAP = {
    "M15": ("minute", 15, 30),
    "H1": ("hour", 1, 120),
    "H4": ("hour", 4, 365),
}


@dataclass(frozen=True)
class AggregateRow:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_csv(self) -> list[str]:
        return [
            self.timestamp.isoformat(),
            f"{self.open:.6f}",
            f"{self.high:.6f}",
            f"{self.low:.6f}",
            f"{self.close:.6f}",
            f"{self.volume:.2f}",
        ]


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download forex aggregates from Massive.com")
    parser.add_argument("--api-key", type=str, default=None, help="Massive API key (falls back to MASSIVE_API_KEY env).")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS), help="Symbols like EURUSD GBPUSD USDJPY.")
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["M15", "H1", "H4"],
        help="Timeframe codes matching Omega config (e.g. M15 H1 H4).",
    )
    parser.add_argument("--start-date", type=str, required=True, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end-date", type=str, required=True, help="End date (YYYY-MM-DD).")
    parser.add_argument("--output-dir", type=Path, default=Path("data"), help="Directory for CSV outputs.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing CSV files.")
    return parser.parse_args(argv)


def request_json(url: str, retries: int = 6, pause: float = 5.0) -> dict:
    req = Request(url, headers={"User-Agent": "omega-fx/massive-downloader"})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(req) as resp:
                payload = resp.read().decode("utf-8")
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < retries - 1:
                retry_after = exc.headers.get("Retry-After")
                wait_for = float(retry_after) if retry_after else 65.0
                wait_for = max(wait_for, pause * (attempt + 1))
                time.sleep(wait_for)
                continue
            if exc.code in {500, 502, 503, 504} and attempt < retries - 1:
                time.sleep(pause * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP error {exc.code}: {exc.reason} ({url})") from exc
        except URLError as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(pause * (attempt + 1))
                continue
            raise RuntimeError(f"Network error: {exc.reason} ({url})") from exc
        try:
            import json

            return json.loads(payload)
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Failed to decode JSON from Massive: {exc}") from exc
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def chunked_ranges(start: date, end: date, chunk_days: int):
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def fetch_aggregates(
    symbol: str,
    timeframe: str,
    start: date,
    end: date,
    api_key: str,
    *,
    adjusted: bool = True,
) -> list[AggregateRow]:
    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(f"Unsupported timeframe '{timeframe}'. Valid: {', '.join(TIMEFRAME_MAP)}")
    timespan, multiplier, chunk_days = TIMEFRAME_MAP[timeframe]
    results: list[AggregateRow] = []
    for chunk_start, chunk_end in chunked_ranges(start, end, chunk_days):
        params = {
            "adjusted": str(adjusted).lower(),
            "sort": "asc",
            "limit": AGG_LIMIT,
            "apiKey": api_key,
        }
        path = (
            f"{BASE_URL}/C:{symbol}/range/"
            f"{multiplier}/{timespan}/{chunk_start.isoformat()}/{chunk_end.isoformat()}"
        )
        url = f"{path}?{urlencode(params)}"
        payload = request_json(url)
        for item in payload.get("results", []):
            timestamp = datetime.fromtimestamp(item["t"] / 1000, tz=timezone.utc)
            results.append(
                AggregateRow(
                    timestamp=timestamp,
                    open=float(item["o"]),
                    high=float(item["h"]),
                    low=float(item["l"]),
                    close=float(item["c"]),
                    volume=float(item.get("v", 0.0)),
                )
            )
        time.sleep(1.0)
    results.sort(key=lambda row: row.timestamp)
    return results


def write_csv(path: Path, rows: list[AggregateRow], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RuntimeError(f"{path} already exists. Use --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for row in rows:
            writer.writerow(row.to_csv())


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = args.api_key or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        print("[!] Provide --api-key or set MASSIVE_API_KEY in the environment.", file=sys.stderr)
        return 1
    try:
        start_date = date.fromisoformat(args.start_date)
        end_date = date.fromisoformat(args.end_date)
    except ValueError as exc:
        print(f"[!] Invalid date: {exc}", file=sys.stderr)
        return 1
    if start_date > end_date:
        print("[!] --start-date must be <= --end-date", file=sys.stderr)
        return 1

    symbols = [sym.upper() for sym in args.symbols]
    timeframes = [tf.upper() for tf in args.timeframes]

    for symbol in symbols:
        for timeframe in timeframes:
            print(f"[+] Fetching {symbol} {timeframe} from {start_date} to {end_date} ...")
            rows = fetch_aggregates(symbol, timeframe, start_date, end_date, api_key)
            if not rows:
                print(f"[!] No data returned for {symbol} {timeframe}.", file=sys.stderr)
                continue
            output_name = f"{symbol}_{timeframe}.csv"
            output_path = (args.output_dir / output_name).resolve()
            write_csv(output_path, rows, overwrite=args.force)
            print(f"[OK] Wrote {len(rows):,} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
