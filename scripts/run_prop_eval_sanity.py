#!/usr/bin/env python3
"""
Prop Firm Evaluation Sanity Check
---------------------------------
Analyzes execution logs to generate a "Pass/Fail" checklist against generic prop firm specifications.

Usage:
    python scripts/run_prop_eval_sanity.py --days 7
    python scripts/run_prop_eval_sanity.py --log path/to/log.csv
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# Generic Prop Firm Specs (can be overridden or made configurable later)
PROP_SPECS = {
    "profit_target_pct": 0.10,      # 10%
    "max_daily_loss_pct": 0.05,     # 5%
    "max_total_loss_pct": 0.10,     # 10%
    "min_trading_days": 5,          # Minimum days to trade
    "max_trading_days": 30,         # Max days to pass (if applicable)
}

def analyze_prop_performance(log_path: Path, days: int) -> int:
    if not log_path.exists():
        print(f"❌ Log file not found: {log_path}")
        return 1

    print(f"Loading log: {log_path}")
    try:
        df = pd.read_csv(log_path)
    except Exception as e:
        print(f"❌ Failed to read log file: {e}")
        return 1

    if df.empty:
        print("❌ Log file is empty.")
        return 1

    # Ensure timestamp is datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Filter by date
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    df = df[df["timestamp"] >= cutoff].copy()
    
    if df.empty:
        print(f"⚠️ No trades found in the last {days} days.")
        return 0

    # --- Metrics Calculation ---

    # 1. Daily PnL & Drawdown
    # We need to reconstruct daily equity snapshots. 
    # Approximation: Use the 'equity' column from the log.
    # Group by date.
    df["date"] = df["timestamp"].dt.date
    
    # Get start of day equity (approximate: first equity of the day)
    # and end of day equity (last equity of the day)
    daily_stats = []
    for date, group in df.groupby("date"):
        start_equity = group.iloc[0]["equity"] 
        # If we have OPEN events, equity might be before trade. 
        # Ideally we'd track balance, but equity is what matters for DD.
        
        min_equity = group["equity"].min()
        end_equity = group.iloc[-1]["equity"]
        
        # Daily Drawdown: (Start Equity - Min Equity) / Start Equity
        # Note: Prop firms usually calculate daily DD based on Balance at start of day vs Equity.
        # Here we use a simplified equity-based approach.
        daily_dd_pct = 0.0
        if start_equity > 0:
            daily_dd_pct = (start_equity - min_equity) / start_equity
            
        daily_pnl = end_equity - start_equity
        
        daily_stats.append({
            "date": date,
            "start_equity": start_equity,
            "end_equity": end_equity,
            "min_equity": min_equity,
            "daily_dd_pct": daily_dd_pct,
            "daily_pnl": daily_pnl
        })
        
    daily_df = pd.DataFrame(daily_stats)
    
    # 2. Total Drawdown
    # High Water Mark logic
    high_water_mark = df["equity"].cummax()
    drawdown = (high_water_mark - df["equity"]) / high_water_mark
    max_total_dd_pct = drawdown.max()
    
    # 3. Risk Per Trade
    # Filter for CLOSE events to see realized risk/reward
    closes = df[df["event"] == "CLOSE"].copy()
    
    avg_risk_pct = 0.0
    max_risk_pct = 0.0
    avg_r_multiple = 0.0
    
    if not closes.empty:
        if "risk_perc" in closes.columns:
            avg_risk_pct = closes["risk_perc"].mean()
            max_risk_pct = closes["risk_perc"].max()
        
        if "r_multiple" in closes.columns:
             avg_r_multiple = closes["r_multiple"].mean()

    # 4. Profit Target Progress
    initial_balance = df.iloc[0]["equity"] # Approx
    current_balance = df.iloc[-1]["equity"]
    total_profit_pct = (current_balance - initial_balance) / initial_balance if initial_balance > 0 else 0.0
    
    # --- Report Generation ---
    
    print(f"\n{'='*60}")
    print(f"PROP EVALUATION REPORT (Last {days} Days)")
    print(f"{'='*60}")
    
    print(f"\n📊 Performance Overview:")
    print(f"  Initial Equity: ${initial_balance:,.2f}")
    print(f"  Current Equity: ${current_balance:,.2f}")
    print(f"  Total Return:   {total_profit_pct:.2%} (Target: {PROP_SPECS['profit_target_pct']:.0%})")
    
    # Checklist
    print(f"\n✅ Prop Firm Checklist:")
    
    # 1. Profit Target
    status = "✅" if total_profit_pct >= PROP_SPECS["profit_target_pct"] else "⏳"
    print(f"  {status} Profit Target: {total_profit_pct:.2%} / {PROP_SPECS['profit_target_pct']:.0%}")
    
    # 2. Daily Drawdown
    worst_daily_dd = daily_df["daily_dd_pct"].max() if not daily_df.empty else 0.0
    status = "✅" if worst_daily_dd < PROP_SPECS["max_daily_loss_pct"] else "❌"
    print(f"  {status} Max Daily DD:  {worst_daily_dd:.2%} < {PROP_SPECS['max_daily_loss_pct']:.0%}")
    
    # 3. Max Total Drawdown
    status = "✅" if max_total_dd_pct < PROP_SPECS["max_total_loss_pct"] else "❌"
    print(f"  {status} Max Total DD:  {max_total_dd_pct:.2%} < {PROP_SPECS['max_total_loss_pct']:.0%}")
    
    # 4. Trading Days
    trading_days = len(daily_df)
    status = "✅" if trading_days >= PROP_SPECS["min_trading_days"] else "⏳"
    print(f"  {status} Trading Days:  {trading_days} / {PROP_SPECS['min_trading_days']} min")

    # 5. Risk Management (Internal Sanity)
    print(f"\n🛡️  Risk Management Sanity:")
    
    status = "✅" if max_risk_pct <= 0.01 else "⚠️" # Warn if > 1% risk per trade
    print(f"  {status} Max Risk/Trade: {max_risk_pct:.2%} (Rec: < 1.0%)")
    
    status = "✅" if avg_risk_pct <= 0.005 else "⚠️" # Warn if > 0.5% avg risk
    print(f"  {status} Avg Risk/Trade: {avg_risk_pct:.2%} (Rec: ~0.25-0.50%)")
    
    status = "✅" if avg_r_multiple >= 1.0 else "⚠️"
    print(f"  {status} Avg R-Multiple: {avg_r_multiple:.2f} (Rec: > 1.0)")

    print(f"\n{'='*60}")
    
    if worst_daily_dd >= PROP_SPECS["max_daily_loss_pct"] or max_total_dd_pct >= PROP_SPECS["max_total_loss_pct"]:
        print("❌ STATUS: FAILED (Hard Limit Breach)")
        return 1
    elif total_profit_pct >= PROP_SPECS["profit_target_pct"] and trading_days >= PROP_SPECS["min_trading_days"]:
        print("🎉 STATUS: PASSED")
        return 0
    else:
        print("⏳ STATUS: IN PROGRESS")
        return 0

def main():
    parser = argparse.ArgumentParser(description="Run Prop Firm Evaluation Sanity Check")
    parser.add_argument("--days", type=int, default=7, help="Number of days to analyze")
    parser.add_argument("--log", type=str, help="Path to execution log CSV")
    
    args = parser.parse_args()
    
    log_path = Path(args.log) if args.log else Path("results/mt5_demo_exec_log.csv")
    
    sys.exit(analyze_prop_performance(log_path, args.days))

if __name__ == "__main__":
    main()
