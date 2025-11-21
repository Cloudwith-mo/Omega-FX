#!/usr/bin/env python3
"""
Download historical market data from Yahoo Finance for Omega FX.
Requires: pip install yfinance
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("[!] This script requires 'yfinance' and 'pandas'.")
    print("    Please run: pip install yfinance pandas")
    sys.exit(1)

DEFAULT_OUTPUT_DIR = Path("data")


def download_data(
    symbol: str,
    days: int,
    interval: str,
    output_dir: Path,
    force: bool = False,
) -> None:
    """
    Fetch data from yfinance and save as CSV in Omega FX format.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Map common forex symbols if needed, or just use raw
    # yfinance expects "EURUSD=X" for forex
    yf_symbol = symbol
    if not symbol.endswith("=X") and len(symbol) == 6 and symbol.isalpha():
         # heuristic for forex pairs like EURUSD -> EURUSD=X
         # But user might pass AAPL, so only apply if it looks like a forex pair
         # For now, let's trust the user input or print a tip.
         pass

    safe_symbol = symbol.replace("=X", "").replace("=", "").upper()
    filename = f"{safe_symbol}_{interval}.csv"
    destination = output_dir / filename

    if destination.exists() and not force:
        print(f"[!] {destination} already exists. Use --force to overwrite.")
        return

    print(f"Downloading {yf_symbol} (last {days} days, {interval})...")
    
    # Calculate start date
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    try:
        df = yf.download(
            tickers=yf_symbol,
            start=start_date,
            end=end_date,
            interval=interval,
            progress=False,
            multi_level_index=False 
        )
    except Exception as e:
        print(f"[!] Error downloading data: {e}")
        return

    if df.empty:
        print(f"[!] No data found for {yf_symbol}. Check the symbol (e.g., use 'EURUSD=X' for forex).")
        return

    # Reset index to get Date/Datetime as a column
    df = df.reset_index()

    # Standardize columns
    # yfinance columns: Date (or Datetime), Open, High, Low, Close, Adj Close, Volume
    # Omega FX expects: timestamp, open, high, low, close, volume
    
    # Rename columns to lowercase
    df.columns = [c.lower() for c in df.columns]
    
    # Handle 'date' vs 'datetime'
    if "date" in df.columns:
        df.rename(columns={"date": "timestamp"}, inplace=True)
    elif "datetime" in df.columns:
        df.rename(columns={"datetime": "timestamp"}, inplace=True)
        
    # Ensure required columns exist
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    
    if missing:
        # Sometimes volume is missing for forex, fill with 0
        if "volume" in missing and len(missing) == 1:
            df["volume"] = 0
        else:
            print(f"[!] Missing columns in yfinance response: {missing}")
            return

    # Select and reorder
    df = df[required]
    
    # Sort by timestamp
    df.sort_values("timestamp", inplace=True)
    
    # Save
    df.to_csv(destination, index=False)
    print(f"Saved {len(df)} rows to {destination}")
    print(f"Preview:\n{df.head(3)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Yahoo Finance data for Omega FX")
    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Ticker symbol (e.g., 'EURUSD=X', 'GBPUSD=X', 'BTC-USD')",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Number of past days to download (default: 60)",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1h",
        choices=["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"],
        help="Data interval (default: 1h)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to save CSVs (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    download_data(
        args.symbol,
        args.days,
        args.interval,
        args.output_dir,
        args.force
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
