#!/usr/bin/env python3
"""
Run a backtest with Prop Firm Evaluation settings to verify risk compliance.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core.backtest import run_backtest
from core.backtest import run_backtest
from config.settings import SYMBOLS, resolve_firm_profile
import argparse
import yaml

def main():
    parser = argparse.ArgumentParser(description="Run Prop Firm Evaluation Backtest")
    parser.add_argument("--profile", choices=["default", "aggressive", "conservative"], default="default", help="Risk/Limit profile")
    args = parser.parse_args()

    print("🚀 Running Prop Firm Evaluation Backtest...")
    print(f"Configuration: PROP_EVAL ({args.profile.upper()})")
    
    # Load limits if profile is not default
    limits = {}
    if args.profile != "default":
        try:
            with open("config/execution_limits.yaml") as f:
                config = yaml.safe_load(f)
                key = f"prop_eval_{args.profile}"
                if key in config:
                    limits = config[key]
                    print(f"  Loaded {args.profile} limits: {limits}")
                else:
                    print(f"  ⚠️ Profile {key} not found in config, using defaults.")
        except Exception as e:
            print(f"  ⚠️ Failed to load limits: {e}")
    
    # Verify profile loading
    profile = resolve_firm_profile("PROP_EVAL")
    print(f"  Max Daily Loss: {profile.prop_max_daily_loss_fraction:.1%}")
    print(f"  Max Total Loss: {profile.prop_max_total_loss_fraction:.1%}")
    print(f"  Internal Daily Stop: {profile.internal_max_daily_loss_fraction:.1%}")
    print(f"  Internal Trailing Stop: {profile.internal_max_trailing_dd_fraction:.1%}")
    
    # Run backtest
    # We use the existing data configuration from settings
    try:
        result = run_backtest(
            firm_profile="PROP_EVAL",
            trading_firm="ftmo", # Just as a base
            account_phase="EVAL",
            entry_mode="H1_ONLY", # Force H1 since we only have H1 data
            symbols_config=SYMBOLS, # Use all configured symbols
        )
    except Exception as e:
        print(f"\n❌ Backtest failed to run: {e}")
        return 1
        
    print("\n📊 Backtest Results:")
    print(f"  Total Return: {result.total_return:.2%}")
    print(f"  Max Drawdown: {result.max_drawdown:.2%}")
    print(f"  Win Rate: {result.win_rate:.1%}")
    print(f"  Trades: {result.number_of_trades}")
    
    print("\n🛡️ Risk Compliance:")
    
    # Check Daily Loss
    max_daily_loss = max(s.max_intraday_dd_fraction for s in result.daily_stats) if result.daily_stats else 0.0
    print(f"  Peak Daily Loss: {max_daily_loss:.2%} (Limit: {profile.prop_max_daily_loss_fraction:.1%})")
    
    if max_daily_loss > profile.prop_max_daily_loss_fraction:
        print("  ❌ FAILED: Daily loss limit exceeded!")
    elif max_daily_loss > profile.internal_max_daily_loss_fraction:
        print("  ⚠️ WARNING: Internal daily stop hit (expected behavior)")
    else:
        print("  ✅ PASSED: Daily loss within limits")
        
    # Check Total Drawdown
    print(f"  Max Total Drawdown: {result.max_drawdown:.2%} (Limit: {profile.prop_max_total_loss_fraction:.1%})")
    
    if result.max_drawdown > profile.prop_max_total_loss_fraction:
        print("  ❌ FAILED: Total drawdown limit exceeded!")
    elif result.max_drawdown > profile.internal_max_trailing_dd_fraction:
        print("  ⚠️ WARNING: Internal trailing stop hit (expected behavior)")
    else:
        print("  ✅ PASSED: Drawdown within limits")
        
    # Check Kill-Switch Triggers
    if result.prop_fail_triggered:
        print(f"  ❌ PROP FAIL TRIGGERED at {result.prop_fail_timestamp}")
    elif result.internal_stop_out_triggered:
        print(f"  ℹ️ Internal Stop-Out Triggered at {result.internal_stop_timestamp}")
    else:
        print("  ✅ No Stop-Outs Triggered")

    return 0

if __name__ == "__main__":
    sys.exit(main())
