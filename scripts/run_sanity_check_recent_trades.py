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

BEHAVIORAL_TARGETS = {
    "OMEGA_M15_TF1": {
        "trades_per_day": (2, 5),
        "sl_pips": (20, 35),
        "tp_pips": (35, 70),
        "hold_minutes": (120, 360),
    },
    "OMEGA_MR_M15": {
        "trades_per_day": (1, 4),
        "sl_pips": (15, 25),
        "tp_pips": (10, 40),
        "hold_minutes": (30, 90),
    },
    # Default for unknown strategies
    "DEFAULT": {
        "trades_per_day": (0, 10),
        "sl_pips": (5, 100),
        "tp_pips": (5, 200),
        "hold_minutes": (5, 1440),
    }
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


def analyze_strategy_behavior(df: pd.DataFrame, hours: int) -> dict:
    """Analyze behavioral metrics per strategy against soft targets."""
    metrics = {}
    
    # Group by strategy
    if "strategy_id" not in df.columns:
        # Fallback if strategy_id missing (older logs)
        df["strategy_id"] = "UNKNOWN"
        
    for strategy_id in df["strategy_id"].unique():
        strat_trades = df[df["strategy_id"] == strategy_id]
        targets = BEHAVIORAL_TARGETS.get(strategy_id, BEHAVIORAL_TARGETS["DEFAULT"])
        
        # Metrics
        days_analyzed = max(hours / 24.0, 1.0)
        trades_per_day = len(strat_trades) / days_analyzed
        
        median_sl = strat_trades["sl_distance_pips"].replace("", float("nan")).astype(float).median()
        median_tp = strat_trades["tp_distance_pips"].replace("", float("nan")).astype(float).median()
        median_hold = strat_trades["hold_seconds"].replace("", float("nan")).astype(float).median()
        median_hold_min = median_hold / 60 if pd.notna(median_hold) else float("nan")
        
        # R-multiples
        r_multiples = strat_trades["r_multiple"].replace("", float("nan")).astype(float)
        avg_r = r_multiples.mean()
        
        # Check soft targets
        flags = []
        t_min, t_max = targets["trades_per_day"]
        if trades_per_day > t_max:
            flags.append(f"High Freq: {trades_per_day:.1f}/day > {t_max}")
        elif trades_per_day < t_min and trades_per_day > 0:
             flags.append(f"Low Freq: {trades_per_day:.1f}/day < {t_min}")
             
        if pd.notna(median_sl):
            s_min, s_max = targets["sl_pips"]
            if median_sl < s_min: flags.append(f"Tight SL: {median_sl:.1f} < {s_min}")
            if median_sl > s_max: flags.append(f"Wide SL: {median_sl:.1f} > {s_max}")
            
        if pd.notna(median_hold_min):
            h_min, h_max = targets["hold_minutes"]
            if median_hold_min < h_min: flags.append(f"Fast Churn: {median_hold_min:.0f}m < {h_min}m")
            if median_hold_min > h_max: flags.append(f"Long Hold: {median_hold_min:.0f}m > {h_max}m")

        metrics[strategy_id] = {
            "trades": len(strat_trades),
            "trades_per_day": trades_per_day,
            "median_sl": median_sl,
            "median_tp": median_tp,
            "median_hold_min": median_hold_min,
            "avg_r": avg_r,
            "flags": flags
        }
        
    return metrics


def main():
    parser = argparse.ArgumentParser(
        description="Sanity check recent trades for HFT-like behavior"
    )
    parser.add_argument("--hours", type=int, default=72, help="Hours to analyze (default: 72)")
    parser.add_argument("--env", choices=["demo", "live"], default="demo", help="Environment")
    parser.add_argument("--log", help="Path to execution log CSV (overrides default)")
    parser.add_argument("--prop-eval", action="store_true", help="Use stricter Prop Firm Evaluation thresholds")
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
    
    if args.prop_eval:
        print("🛡️  Using Stricter Prop Firm Evaluation Thresholds")
        # Override with stricter defaults if not explicitly in config
        # Ideally these should come from config, but for now we harden them here
        limits["min_hold_seconds"] = max(limits.get("min_hold_seconds", 600), 1800) # Min 30 mins
        limits["max_trades_per_symbol_per_hour"] = min(limits.get("max_trades_per_symbol_per_hour", 2), 1) # Max 1/hour
        
    result = analyze_trades(log_path, args.hours, limits)
    
    print(f"\n{'='*60}")
    print(f"SANITY CHECK: Last {args.hours} hours ({args.env})")
    print(f"Log: {log_path}")
    print(f"{'='*60}")
    
    if result["status"] == "NO_TRADES":
        print("\n✅ No trades to analyze")
        return 0
    
    print(f"\nTrades analyzed: {result['trades_analyzed']}\n")
    
    # Safety Rail Checks
    print("--- SAFETY RAILS (HARD LIMITS) ---")
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
    
    # Behavioral Checks
    print("--- BEHAVIORAL TARGETS (SOFT LIMITS) ---")
    df = pd.read_csv(log_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    recent_closes = df[(df["timestamp"] >= cutoff) & (df["event"] == "CLOSE")].copy()
    
    if not recent_closes.empty:
        behavior_metrics = analyze_strategy_behavior(recent_closes, args.hours)
        for strategy, m in behavior_metrics.items():
            status = "⚠️" if m["flags"] else "OK"
            print(f"[{status}] {strategy}:")
            print(f"  Trades/Day: {m['trades_per_day']:.1f}")
            print(f"  Med SL/TP: {m['median_sl']:.1f} / {m['median_tp']:.1f} pips")
            print(f"  Med Hold: {m['median_hold_min']:.0f} min")
            print(f"  Avg R: {m['avg_r']:.2f}R")
            if m["flags"]:
                for f in m["flags"]:
                    print(f"    - {f}")
            print()
    else:
        print("No completed trades to analyze behavior.")

    if has_violations:
        print("=" * 60)
        print("❌ SANITY CHECK FAILED: Violations detected")
        print("=" * 60)
        return 1
    else:
        print("=" * 60)
        print("✅ SANITY CHECK PASSED (Safety Rails)")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
