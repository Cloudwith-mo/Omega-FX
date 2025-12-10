#!/usr/bin/env python3
"""Quick demo performance checker."""

import json
import sys
from pathlib import Path

import pandas as pd

# Expected paths (adjust if your VPS uses different paths)
SUMMARY_PATH = Path("results/mt5_demo_exec_live_summary.json")
LOG_PATH = Path("results/mt5_demo_exec_log.csv")
BACKTEST_SUMMARY = Path("results/minimal_ftmo_eval_summary.json")


def check_demo_performance():
    """Analyze demo trading performance."""
    print("=" * 70)
    print("OMEGA FX DEMO PERFORMANCE REPORT")
    print("=" * 70)
    print()

    # Check if files exist
    if not SUMMARY_PATH.exists():
        print(f"❌ Summary file not found: {SUMMARY_PATH}")
        print()
        print("This means either:")
        print("1. The bot hasn't run yet")
        print("2. The bot is running on a VPS (check there)")
        print("3. The output path is different")
        print()
        print("To check on VPS:")
        print("  ssh your-vps-ip")
        print(f"  cd /path/to/Omega-FX")
        print(f"  python scripts/check_demo_progress.py")
        return 1

    if not LOG_PATH.exists():
        print(f"❌ Log file not found: {LOG_PATH}")
        return 1

    # Load summary
    with open(SUMMARY_PATH) as f:
        summary = json.load(f)

    # Load trade log
    trades_df = pd.read_csv(LOG_PATH)

    # Load backtest for comparison
    backtest_summary = {}
    if BACKTEST_SUMMARY.exists():
        with open(BACKTEST_SUMMARY) as f:
            backtest_summary = json.load(f)

    print("📊 PERFORMANCE SUMMARY")
    print("-" * 70)

    # Session info
    session_id = summary.get("session_id", "unknown")
    risk_env = summary.get("risk_env", "unknown")
    risk_tier = summary.get("risk_tier", "unknown")
    print(f"Session: {session_id}")
    print(f"Environment: {risk_env.upper()}")
    print(f"Risk Tier: {risk_tier.title()}")
    print()

    # Equity metrics
    start_equity = summary.get("session_start_equity", 100_000)
    end_equity = summary.get("session_end_equity", start_equity)
    session_pnl = end_equity - start_equity
    session_pnl_pct = (session_pnl / start_equity * 100) if start_equity else 0

    print("💰 EQUITY")
    print(f"Starting Equity:  ${start_equity:,.2f}")
    print(f"Current Equity:   ${end_equity:,.2f}")
    print(f"Session P&L:      ${session_pnl:+,.2f} ({session_pnl_pct:+.2f}%)")
    print()

    # Trade stats
    num_trades = summary.get("number_of_trades", 0)
    win_rate = summary.get("win_rate", 0) * 100
    avg_pnl = summary.get("average_pnl_per_trade", 0)

    print("📈 TRADE STATISTICS")
    print(f"Total Trades:     {num_trades}")
    print(f"Win Rate:         {win_rate:.1f}%")
    print(f"Avg P&L/Trade:    ${avg_pnl:,.2f}")
    print()

    # Risk metrics
    max_dd = summary.get("max_drawdown_pct", 0) * 100
    daily_loss_24h = summary.get("last_24h_pnl", 0)

    print("⚠️  RISK METRICS")
    print(f"Max Drawdown:     {max_dd:.2f}%")
    print(f"Last 24h P&L:     ${daily_loss_24h:+,.2f}")
    print()

    # Compare to backtest
    if backtest_summary:
        bt_win_rate = (backtest_summary.get("win_rate", 0) or 0) * 100
        bt_avg_pnl = backtest_summary.get("average_pnl_per_trade", 0)
        
        print("🔬 LIVE vs BACKTEST")
        print(f"Win Rate:         Live {win_rate:.1f}% vs Backtest {bt_win_rate:.1f}%")
        print(f"Avg P&L/Trade:    Live ${avg_pnl:.2f} vs Backtest ${bt_avg_pnl:.2f}")
        
        win_rate_diff = abs(win_rate - bt_win_rate)
        if win_rate_diff > 15:
            print(f"⚠️  WARNING: Win rate differs by {win_rate_diff:.1f}% (investigate!)")
        else:
            print(f"✅ Win rate within acceptable range (±{win_rate_diff:.1f}%)")
        print()

    # Filter analysis
    filters = summary.get("filter_counts", {})
    if filters:
        print("🚫 FILTERS (Why trades were blocked)")
        for filter_name, count in sorted(filters.items()):
            if count > 0:
                print(f"  {filter_name}: {count}")
        print()

    # Strategy breakdown
    per_strategy = summary.get("per_strategy", {})
    if per_strategy:
        print("📊 STRATEGY BREAKDOWN")
        for strategy_id, stats in sorted(per_strategy.items()):
            strat_trades = stats.get("trades", 0)
            strat_wins = stats.get("wins", 0)
            strat_wr = (strat_wins / strat_trades * 100) if strat_trades else 0
            strat_pnl = stats.get("pnl", 0)
            print(f"  {strategy_id}: {strat_trades} trades, {strat_wr:.1f}% WR, ${strat_pnl:+,.2f}")
        print()

    # Health check
    print("=" * 70)
    print("🏥 HEALTH CHECK")
    print("=" * 70)

    issues = []
    warnings = []

    # Check drawdown
    if max_dd > 5:
        issues.append(f"❌ Max drawdown {max_dd:.2f}% exceeds 5% target")
    elif max_dd > 3:
        warnings.append(f"⚠️  Max drawdown {max_dd:.2f}% is elevated (target < 3%)")
    else:
        print(f"✅ Drawdown {max_dd:.2f}% is healthy (< 3%)")

    # Check win rate
    if win_rate < 35:
        issues.append(f"❌ Win rate {win_rate:.1f}% is too low (target 45-55%)")
    elif win_rate < 40:
        warnings.append(f"⚠️  Win rate {win_rate:.1f}% is below target (45-55%)")
    elif win_rate > 65:
        warnings.append(f"⚠️  Win rate {win_rate:.1f}% is suspiciously high (verify data)")
    else:
        print(f"✅ Win rate {win_rate:.1f}% is in target range (45-55%)")

    # Check session PnL
    if session_pnl_pct > 10:
        warnings.append(f"⚠️  Session P&L {session_pnl_pct:+.2f}% is very high (variance?)")
    elif session_pnl_pct < -5:
        issues.append(f"❌ Session P&L {session_pnl_pct:+.2f}% is too negative")
    else:
        print(f"✅ Session P&L {session_pnl_pct:+.2f}% is reasonable")

    # Check trade count
    if num_trades < 10:
        warnings.append(f"⚠️  Only {num_trades} trades - need more data for reliable stats")
    elif num_trades > 500:
        warnings.append(f"⚠️  {num_trades} trades is very high - verify session duration")
    else:
        print(f"✅ Trade count {num_trades} is reasonable")

    print()

    if warnings:
        print("⚠️  WARNINGS:")
        for w in warnings:
            print(f"  {w}")
        print()

    if issues:
        print("❌ ISSUES:")
        for i in issues:
            print(f"  {i}")
        print()
        print("🔧 RECOMMENDATION: Investigate issues before buying evaluations")
    elif warnings:
        print("🔧 RECOMMENDATION: Monitor warnings but generally OK to proceed")
    else:
        print("🎉 RECOMMENDATION: Performance looks good! Consider buying evaluations")

    print()
    print("=" * 70)
    print()

    # Show recent trades
    if len(trades_df) > 0:
        print("📜 RECENT TRADES (Last 10)")
        print("-" * 70)
        recent = trades_df.tail(10)
        for _, trade in recent.iterrows():
            symbol = trade.get("symbol", "unknown")
            direction = trade.get("direction", "?")
            pnl = trade.get("pnl", 0)
            timestamp = trade.get("timestamp", "?")
            print(f"  {timestamp} | {symbol:6s} | {direction:5s} | ${pnl:+8.2f}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(check_demo_performance())
