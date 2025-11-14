#!/usr/bin/env python3
"""Aggregate trade performance by session/volatility/trend tags."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


GROUP_COLUMNS = [
    ["session_tag"],
    ["volatility_regime"],
    ["trend_regime"],
]


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    equity = values.cumsum()
    running_max = equity.cummax()
    dd = (running_max - equity).max()
    return float(dd) if pd.notna(dd) else 0.0


def summarize_group(group: pd.DataFrame) -> dict:
    wins = (group["r_multiple"] > 0).mean() if not group.empty else 0.0
    expectancy = group["r_multiple"].mean() if not group.empty else 0.0
    dd = max_drawdown(group.sort_values("entry_time")["r_multiple"])
    return {
        "n_trades": len(group),
        "win_rate": wins,
        "avg_r_multiple": expectancy,
        "expectancy": expectancy,
        "max_dd_r_multiple": dd,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze trades by tags.")
    parser.add_argument(
        "--trades_path",
        type=Path,
        default=Path("outputs/trades.csv"),
        help="Path to enriched trades CSV",
    )
    parser.add_argument(
        "--min_trades",
        type=int,
        default=10,
        help="Minimum trades per bucket to include in ranking output",
    )
    parser.add_argument(
        "--top_k",
        type=int,
        default=20,
        help="Number of rows to show in top/bottom lists",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/trade_edge_map.csv"),
        help="Where to save the aggregated metrics",
    )
    args = parser.parse_args()

    if not args.trades_path.exists():
        raise SystemExit(f"Trades file not found: {args.trades_path}")

    df = pd.read_csv(args.trades_path)
    if df.empty:
        raise SystemExit("Trades file is empty; run the backtest first.")

    if "r_multiple" not in df.columns:
        raise SystemExit("Trades file missing r_multiple column. Re-run backtest after Step 4.1.")

    all_results: list[pd.DataFrame] = []
    combo_cols = ["session_tag", "trend_regime", "volatility_regime", "pattern_tag"]
    grouped = df.groupby(combo_cols, dropna=False)
    rows = []
    for keys, group in grouped:
        result = summarize_group(group)
        for col, value in zip(combo_cols, keys):
            result[col] = value
        result["grouping"] = "+".join(combo_cols)
        rows.append(result)
    all_results.append(pd.DataFrame(rows))

    if not all_results:
        raise SystemExit("No grouped results generated.")

    combined = pd.concat(all_results, ignore_index=True)
    combined.to_csv(args.output, index=False)
    print(f"Saved analysis to {args.output}")

    ranking_source = combined[combined["n_trades"] >= args.min_trades].copy()
    if ranking_source.empty:
        print("Not enough trades per bucket for ranked summary.")
        return

    ranking_source = ranking_source.sort_values("expectancy", ascending=False)
    top_k = ranking_source.head(args.top_k)
    bottom_k = ranking_source.tail(args.top_k)

    print("\nTop buckets by expectancy:")
    for _, row in top_k.iterrows():
        tags = [f"{col}={row[col]}" for col in ["session_tag", "trend_regime", "volatility_regime", "pattern_tag"]]
        print(
            f"{' '.join(tags)} | n={row['n_trades']} | "
            f"win_rate={row['win_rate']:.2%} | expectancy={row['expectancy']:.2f}R | maxDD={row['max_dd_r_multiple']:.2f}R"
        )

    print("\nBottom buckets by expectancy:")
    for _, row in bottom_k.iterrows():
        tags = [f"{col}={row[col]}" for col in ["session_tag", "trend_regime", "volatility_regime", "pattern_tag"]]
        print(
            f"{' '.join(tags)} | n={row['n_trades']} | "
            f"win_rate={row['win_rate']:.2%} | expectancy={row['expectancy']:.2f}R | maxDD={row['max_dd_r_multiple']:.2f}R"
        )


if __name__ == "__main__":
    main()
