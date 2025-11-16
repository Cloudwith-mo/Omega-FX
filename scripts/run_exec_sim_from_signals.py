#!/usr/bin/env python3
"""Replay Omega trades through the simulated execution backend."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - CLI convenience
    sys.path.insert(0, str(REPO_ROOT))

from config.deploy_ftmo_eval import FTMO_EVAL_PRESET  # noqa: E402
from core.backtest import run_backtest  # noqa: E402
from core.execution_base import OrderSpec  # noqa: E402
from core.position_sizing import calculate_position_size  # noqa: E402
from core.risk import RISK_PROFILES, RiskMode  # noqa: E402
from execution_backends.simulated import SimulatedExecutionBackend  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulated execution replay using Omega signals.")
    parser.add_argument("--starting_equity", type=float, default=100_000.0, help="Initial equity for sizing.")
    parser.add_argument(
        "--limit_trades",
        type=int,
        default=None,
        help="Optional cap on number of trades to replay (after closing).",
    )
    parser.add_argument(
        "--summary_path",
        type=Path,
        default=Path("results/execution_sim_summary.json"),
        help="Destination for execution summary JSON.",
    )
    parser.add_argument(
        "--log_path",
        type=Path,
        default=Path("results/execution_sim_log.csv"),
        help="CSV log path for simulated fills.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backtest = run_backtest(
        df=None,
        starting_equity=args.starting_equity,
        data_source=None,
        symbol_data_map=None,
        entry_mode=FTMO_EVAL_PRESET.entry_mode,
        trading_firm=FTMO_EVAL_PRESET.trading_firm,
        account_phase=FTMO_EVAL_PRESET.account_phase,
    )

    backend = SimulatedExecutionBackend(initial_equity=args.starting_equity, log_path=args.log_path)
    backend.connect()

    events = []
    for idx, trade in enumerate(backtest.trades):
        entry_time = _to_datetime(trade["entry_time"])
        exit_time = _to_datetime(trade["exit_time"])
        events.append((entry_time, "open", idx, trade))
        events.append((exit_time, "close", idx, trade))
    events.sort(key=lambda item: (item[0], 0 if item[1] == "open" else 1))

    tickets: dict[int, str] = {}
    closed = 0

    for timestamp, kind, trade_id, trade in events:
        if kind == "open":
            risk_mode = RiskMode(trade["risk_mode_at_entry"])
            base_fraction = RISK_PROFILES[risk_mode].risk_per_trade_fraction
            risk_fraction = base_fraction * float(trade.get("risk_scale", 1.0))
            if risk_fraction <= 0:
                continue
            try:
                volume = calculate_position_size(
                    equity=backend.current_equity,
                    risk_fraction=risk_fraction,
                    entry_price=float(trade["entry_price"]),
                    stop_price=float(trade["stop_loss"]),
                    symbol=trade["symbol"],
                )
            except ValueError:
                continue
            spec = OrderSpec(
                symbol=trade["symbol"],
                direction=trade["direction"],
                volume=volume,
                entry_price=float(trade["entry_price"]),
                stop_loss=float(trade["stop_loss"]),
                take_profit=float(trade["take_profit"]),
                timestamp=timestamp,
                tag=trade.get("pattern_tag", "OMEGA_FX"),
            )
            tickets[trade_id] = backend.submit_order(spec)
        else:
            ticket = tickets.get(trade_id)
            if not ticket:
                continue
            backend.close_position(
                ticket,
                trade.get("reason", "EXIT"),
                close_price=float(trade["exit_price"]),
                timestamp=timestamp,
            )
            closed += 1
            if args.limit_trades and closed >= args.limit_trades:
                break

    summary = backend.summary()
    args.summary_path.parent.mkdir(parents=True, exist_ok=True)
    args.summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


def _to_datetime(value) -> pd.Timestamp:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return pd.to_datetime(value).to_pydatetime()


if __name__ == "__main__":
    raise SystemExit(main())
