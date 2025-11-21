#!/usr/bin/env python3
"""
Sanity check recent trades to detect HFT-like behavior.

Usage:
    python scripts/run_sanity_check_recent_trades.py --hours 72 --env demo
    python scripts/run_sanity_check_recent_trades.py --hours 24 --log path/to/custom_log.csv
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml


def load_safety_limits():
    """Load thresholds from config/execution_limits.yaml."""
    config_path = Path("config/execution_limits.yaml")
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)["safety_rails"]
    
    # Fallback defaults
    return {
        "max_trades_per_symbol_per_hour": 2,
        "min_sl_pips": {"default": 10},
        "min_hold_seconds": 600,
    }


def analyze_trades(log_path: Path, hours: int, limits: dict) -> dict:
    """Analyze recent trades and return metrics with violation flags."""
    df = pd.read_csv(log_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Filter to recent trades
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = df[df["timestamp"] >= cutoff]
    
    # Only analyze CLOSE events (completed trades)
    closes = recent[recent["event"] == "CLOSE"].copy()
    
    if closes.empty:
        return {"status": "NO_TRADES", "trades_analyzed": 0}
    
    # Compute metrics per symbol
    metrics = {}
    
    for symbol in closes["symbol"].unique():
        symbol_trades = closes[closes["symbol"] == symbol]
        
        trades_per_hour = len(symbol_trades) / hours
        median_sl = symbol_trades["sl_distance_pips"].replace("", float("nan")).astype(float).median()
        median_hold = symbol_trades["hold_seconds"].replace("", float("nan")).astype(float).median()
        
        # Check thresholds
        min_sl = limits["min_sl_pips"].get(symbol, limits["min_sl_pips"]["default"])
        min_hold = limits["min_hold_seconds"]
        max_tph = limits["max_trades_per_symbol_per_hour"]
        
        violations = []
        if trades_per_hour > max_tph:
            violations.append(f"trades/hour={trades_per_hour:.1f} > {max_tph}")
        if not pd.isna(median_sl) and median_sl < min_sl:
            violations.append(f"median_sl={median_sl:.1f}pips < {min_sl}pips")
        if not pd.isna(median_hold) and median_hold < min_hold:
            violations.append(f"median_hold={median_hold:.0f}s < {min_hold}s")
        
        metrics[symbol] = {
            "trades": len(symbol_trades),
            "trades_per_hour": trades_per_hour,
            "median_sl_pips": median_sl,
            "median_hold_seconds": median_hold,
            "violations": violations,
        }
    
    return {
        "status": "VIOLATIONS" if any(m["violations"] for m in metrics.values()) else "OK",
        "trades_analyzed": len(closes),
        "per_symbol": metrics,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sanity check recent trades for HFT-like behavior"
    )
    parser.add_argument("--hours", type=int, default=72, help="Hours to analyze (default: 72)")
    parser.add_argument("--env", choices=["demo", "live"], default="demo", help="Environment")
    parser.add_argument("--log", help="Path to execution log CSV (overrides default)")
    args = parser.parse_args()
    
    # Determine log path
    if args.log:
        log_path = Path(args.log)
    else:
        log_path = Path("results/mt5_demo_exec_log.csv")
    
    if not log_path.exists():
        print(f"❌ Log file not found: {log_path}")
        return 1
    
    limits = load_safety_limits()
    result = analyze_trades(log_path, args.hours, limits)
    
    print(f"\n{'='*60}")
    print(f"SANITY CHECK: Last {args.hours} hours ({args.env})")
    print(f"Log: {log_path}")
    print(f"{'='*60}")
    
    if result["status"] == "NO_TRADES":
        print("\n✅ No trades to analyze")
        return 0
    
    print(f"\nTrades analyzed: {result['trades_analyzed']}\n")
    
    has_violations = False
    for symbol, metrics in result["per_symbol"].items():
        status = "❌" if metrics["violations"] else "✅"
        print(f"{status} {symbol}:")
        print(f"  Trades: {metrics['trades']}")
        print(f"  Trades/hour: {metrics['trades_per_hour']:.2f}")
        
        if pd.notna(metrics['median_sl_pips']):
            print(f"  Median SL: {metrics['median_sl_pips']:.1f} pips")
        else:
            print(f"  Median SL: N/A")
        
        if pd.notna(metrics['median_hold_seconds']):
            print(f"  Median hold: {metrics['median_hold_seconds']/60:.1f} minutes")
        else:
            print(f"  Median hold: N/A")
        
        if metrics["violations"]:
            has_violations = True
            print(f"  ⚠️  VIOLATIONS:")
            for v in metrics["violations"]:
                print(f"    - {v}")
        print()
    
    if has_violations:
        print("=" * 60)
        print("❌ SANITY CHECK FAILED: Violations detected")
        print("=" * 60)
        return 1
    else:
        print("=" * 60)
        print("✅ SANITY CHECK PASSED")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
