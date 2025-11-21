#!/usr/bin/env python3
"""
Demo script showing export_recent_logs.py usage.

Creates a sample execution log and exports it using the CLI tool.
"""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

def create_demo_log():
    """Create a sample execution log for demonstration."""
    log_path = Path("results/demo_exec_log_sample.csv")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    now = datetime.now(timezone.utc)
    fieldnames = [
        "timestamp", "event", "ticket", "symbol", "direction",
        "volume", "price", "equity", "pnl", "data_mode",
        "strategy_id", "session_id", "signal_reason"
    ]
    
    rows = []
    
    # Generate sample trades over 4 days
    for day in range(4):
        for trade in range(5):
            ts = now - timedelta(days=day, hours=trade * 2)
            is_win = (day + trade) % 3 != 0  # 2/3 win rate
            pnl = 75.0 if is_win else -35.0
            
            # OPEN event
            rows.append({
                "timestamp": ts.isoformat(),
                "event": "OPEN",
                "ticket": f"{day}_{trade}",
                "symbol": ["EURUSD", "GBPUSD", "USDJPY"][trade % 3],
                "direction": ["long", "short"][trade % 2],
                "volume": "1.0",
                "price": "1.1000",
                "equity": f"{100000 + day * 100}",
                "pnl": "",
                "data_mode": "live",
                "strategy_id": ["OMEGA_M15_TF1", "OMEGA_MR_M15"][day % 2],
                "session_id": f"demo_session_{day}",
                "signal_reason": "H1_TREND_CONF",
            })
            
            # CLOSE event (30 min later)
            rows.append({
                "timestamp": (ts + timedelta(minutes=30)).isoformat(),
                "event": "CLOSE",
                "ticket": f"{day}_{trade}",
                "symbol": ["EURUSD", "GBPUSD", "USDJPY"][trade % 3],
                "direction": ["long", "short"][trade % 2],
                "volume": "1.0",
                "price": "1.1050" if is_win else "1.0965",
                "equity": f"{100000 + day * 100 + pnl}",
                "pnl": str(pnl),
                "data_mode": "live",
                "strategy_id": ["OMEGA_M15_TF1", "OMEGA_MR_M15"][day % 2],
                "session_id": f"demo_session_{day}",
                "signal_reason": "",
            })
    
    with log_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"✅ Created sample log: {log_path}")
    print(f"   Total events: {len(rows)}")
    print(f"   Time span: {rows[0]['timestamp']} to {rows[-1]['timestamp']}")
    return log_path


def run_export_demo(log_path: Path):
    """Run export_recent_logs.py with demo data."""
    print("\n" + "="*70)
    print("DEMO: Export last 48 hours")
    print("="*70 + "\n")
    
    cmd = [
        sys.executable,
        "scripts/export_recent_logs.py",
        "--hours", "48",
        "--env", "demo",
        "--log-path", str(log_path),
    ]
    
    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=Path.cwd())
    
    return result.returncode


def main():
    print("Export Recent Logs - Demo\n")
    
    # Create sample data
    log_path = create_demo_log()
    
    # Run export
    exit_code = run_export_demo(log_path)
    
    if exit_code == 0:
        print("\n✅ Demo completed successfully!")
        print("\nNext steps:")
        print("1. Check the exported CSV in results/")
        print("2. Try: python scripts/export_recent_logs.py --days 3 --env demo")
        print("3. Try: python scripts/export_recent_logs.py --help")
    else:
        print(f"\n❌ Demo failed with exit code {exit_code}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
