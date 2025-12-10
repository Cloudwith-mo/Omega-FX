import pandas as pd
import sys

log_path = "results/data_exports/exec_log_last_30d_demo.csv"

try:
    df = pd.read_csv(log_path)
except Exception as e:
    print(f"Error reading CSV: {e}")
    sys.exit(1)

print(f"Total rows: {len(df)}")
print(f"Columns: {list(df.columns)}")

if "data_mode" in df.columns:
    print(f"\nData Modes:\n{df['data_mode'].value_counts()}")

if "event" in df.columns:
    print(f"\nEvents:\n{df['event'].value_counts()}")

if "equity" in df.columns:
    df["equity"] = pd.to_numeric(df["equity"], errors="coerce")
    print(f"\nEquity Stats:")
    print(f"  Min: {df['equity'].min()}")
    print(f"  Max: {df['equity'].max()}")
    print(f"  Start: {df['equity'].iloc[0] if not df.empty else 'N/A'}")
    print(f"  End: {df['equity'].iloc[-1] if not df.empty else 'N/A'}")
    
    # Find largest drops
    df["prev_equity"] = df["equity"].shift(1)
    df["equity_change"] = df["equity"] - df["prev_equity"]
    
    print("\nLargest Equity Drops:")
    drops = df[df["equity_change"] < -10].sort_values("equity_change").head(10)
    for _, row in drops.iterrows():
        print(f"  {row['timestamp']} | {row['event']} | {row['ticket']} | Change: {row['equity_change']:.2f} | Equity: {row['equity']:.2f}")

# Check for orphan CLOSE events
if "event" in df.columns and "ticket" in df.columns:
    opens = set(df[df["event"] == "OPEN"]["ticket"])
    closes = set(df[df["event"] == "CLOSE"]["ticket"])
    
    orphans = closes - opens
    print(f"\nOrphan CLOSE events (no matching OPEN): {len(orphans)}")
    if orphans:
        print(f"Sample orphans: {list(orphans)[:5]}")
