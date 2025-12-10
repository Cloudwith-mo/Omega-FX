#!/usr/bin/env python3
"""Download public EURUSD H1 sample data for Omega FX."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

RAW_URL = "https://raw.githubusercontent.com/mohammad95labbaf/EURUSD_LSTM_Attention/main/EURUSD_H1.csv"
DEFAULT_OUTPUT = Path("data/eurusd_h1.csv")


def _ensure_header(content: bytes) -> bytes:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover
        raise RuntimeError("Downloaded file is not valid UTF-8 text.") from exc

    stripped = text.lstrip()
    if not stripped.lower().startswith("timestamp"):
        text = "timestamp,open,high,low,close,volume\n" + stripped
    return text.encode("utf-8")


def download_file(url: str, destination: Path, force: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        print(f"[!] {destination} already exists. Use --force to overwrite.")
        return

    print(f"Downloading EURUSD_H1.csv from {url}...")
    try:
        with urlopen(url) as response:
            data = response.read()
    except HTTPError as exc:  # pragma: no cover
        raise RuntimeError(
            f"HTTP error {exc.code} while downloading: {exc.reason}"
        ) from exc
    except URLError as exc:  # pragma: no cover
        raise RuntimeError(f"Failed to reach server: {exc.reason}") from exc

    destination.write_bytes(_ensure_header(data))
    print(f"Saved to {destination}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download example EURUSD H1 CSV")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Destination file path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination file if it already exists.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=RAW_URL,
        help="Source URL for the EURUSD H1 CSV.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        download_file(args.url, args.output, force=args.force)
    except RuntimeError as exc:
        print(f"[!] Download failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
