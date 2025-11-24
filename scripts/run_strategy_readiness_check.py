#!/usr/bin/env python3
"""Lightweight readiness checks for configured symbols per bot.

Checks:
- File existence for H1/M15/H4 paths in settings.SYMBOLS
- Non-empty data and timestamp range
- Basic OHLC sanity (min/max close)

Usage:
  python scripts/run_strategy_readiness_check.py --bot demo_trend_only
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - CLI entry
    sys.path.insert(0, str(REPO_ROOT))

from config.settings import SYMBOLS


def load_info(path: Path) -> dict:
    info = {"path": path, "exists": path.exists(), "rows": 0, "start": None, "end": None, "min_close": None, "max_close": None}
    if not info["exists"]:
        return info
    try:
        df = pd.read_csv(path, sep=None, engine="python")
        info["rows"] = len(df)
        if info["rows"] > 0:
            cols = [c.strip().lower() for c in df.columns]
            df.columns = cols
            if "<date>" in cols and "<time>" in cols:
                df["timestamp"] = pd.to_datetime(df["<date>"] + " " + df["<time>"], errors="coerce")
            elif "timestamp" in cols:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            else:
                df["timestamp"] = pd.to_datetime(df.iloc[:, 0], errors="coerce")
            ts_col = "timestamp"
            close_col = None
            for candidate in ("close", "<close>"):
                if candidate in cols:
                    close_col = candidate
                    break
            df = df.dropna(subset=[ts_col])
            info["start"] = df[ts_col].min()
            info["end"] = df[ts_col].max()
            if close_col in df.columns:
                info["min_close"] = pd.to_numeric(df[close_col], errors="coerce").min()
                info["max_close"] = pd.to_numeric(df[close_col], errors="coerce").max()
    except Exception as exc:  # pragma: no cover - CLI guard
        info["error"] = str(exc)
    return info



def check_symbol(sym_cfg) -> dict:
    paths = {
        "H1": Path(sym_cfg.h1_path),
        "M15": Path(sym_cfg.m15_path) if sym_cfg.m15_path else None,
        "H4": Path(sym_cfg.h4_path) if sym_cfg.h4_path else None,
    }
    details: Dict[str, dict] = {}
    warnings: List[str] = []
    for label, p in paths.items():
        if p is None:
            continue
        info = load_info(p)
        details[label] = info
        if not info["exists"]:
            warnings.append(f"{label}: missing file {p}")
        elif info.get("error"):
            warnings.append(f"{label}: error reading {p} -> {info['error']}")
        elif info["rows"] == 0:
            warnings.append(f"{label}: empty file {p}")
    return {"details": details, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description="Strategy readiness checker")
    parser.add_argument("--bot", required=True, help="Bot name for labeling only")
    args = parser.parse_args()

    print(f"=== Strategy Readiness: {args.bot} ===")
    ok_symbols = []
    for sym_cfg in SYMBOLS:
        result = check_symbol(sym_cfg)
        warnings = result["warnings"]
        if warnings:
            print(f"[WARN] {sym_cfg.name}: {', '.join(warnings)}")
        else:
            ok_symbols.append(sym_cfg.name)
            print(f"[OK] {sym_cfg.name}")
        for timeframe, info in result["details"].items():
            if not info["exists"]:
                continue
            start = info["start"]
            end = info["end"]
            rows = info["rows"]
            print(f"  {timeframe}: rows={rows} start={start} end={end} close[min,max]={info['min_close']},{info['max_close']}")
    print(f"OK symbols: {', '.join(ok_symbols) if ok_symbols else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
