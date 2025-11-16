#!/usr/bin/env python3
"""Replay Omega signals through the MT5 demo backend."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from config.deploy_ftmo_eval import FTMO_EVAL_PRESET  # noqa: E402
from core.backtest import run_backtest  # noqa: E402
from core.execution_base import OrderSpec  # noqa: E402
from core.execution_accounts import available_profile_names, resolve_account_config  # noqa: E402
from core.position_sizing import calculate_position_size  # noqa: E402
from core.risk import RISK_PROFILES, RiskMode  # noqa: E402
from execution_backends.mt5_demo import Mt5DemoExecutionBackend  # noqa: E402


def parse_args() -> argparse.Namespace:
    profile_choices = available_profile_names()
    parser = argparse.ArgumentParser(description="Route Omega trades to an MT5 demo account.")
    parser.add_argument("--starting_equity", type=float, default=100_000.0)
    parser.add_argument(
        "--dry_run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep true to log only; use --no-dry-run to submit real demo orders.",
    )
    parser.add_argument(
        "--account_profile",
        choices=profile_choices if profile_choices else None,
        default=None,
        help="Named MT5 profile from config/mt5_accounts.yaml",
    )
    parser.add_argument("--max_positions", type=int, default=2)
    parser.add_argument("--per_trade_risk_fraction", type=float, default=0.004)
    parser.add_argument("--daily_loss_fraction", type=float, default=0.02)
    parser.add_argument("--summary_path", type=Path, default=Path("results/mt5_demo_exec_summary.json"))
    parser.add_argument("--log_path", type=Path, default=Path("results/mt5_demo_exec_log.csv"))
    parser.add_argument("--limit_trades", type=int, default=None, help="Optional cap on trade count.")
    parser.add_argument("--login", type=int, default=None)
    parser.add_argument("--server", type=str, default=None)
    parser.add_argument("--password", type=str, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    account = resolve_account_config(
        args.account_profile,
        login=args.login,
        password=args.password,
        server=args.server,
    )
    if not account.server:
        raise RuntimeError("MT5 server is required via profile, env, or CLI arguments.")

    backtest = run_backtest(
        df=None,
        starting_equity=args.starting_equity,
        entry_mode=FTMO_EVAL_PRESET.entry_mode,
        trading_firm=FTMO_EVAL_PRESET.trading_firm,
        account_phase=FTMO_EVAL_PRESET.account_phase,
    )

    backend = Mt5DemoExecutionBackend(
        login=account.login,
        password=account.password,
        server=account.server,
        dry_run=args.dry_run,
        max_positions=args.max_positions,
        per_trade_risk_fraction=args.per_trade_risk_fraction,
        daily_loss_fraction=args.daily_loss_fraction,
        log_path=args.log_path,
        summary_path=args.summary_path,
    )
    backend.connect()

    events = []
    for idx, trade in enumerate(backtest.trades):
        entry_time = _to_datetime(trade["entry_time"])
        exit_time = _to_datetime(trade["exit_time"])
        events.append((entry_time, "open", idx, trade))
        events.append((exit_time, "close", idx, trade))
    events.sort(key=lambda evt: (evt[0], 0 if evt[1] == "open" else 1))

    tickets: dict[int, str] = {}
    closed = 0
    try:
        for timestamp, kind, trade_id, trade in events:
            if kind == "open":
                ticket = _submit_from_trade(backend, trade, timestamp)
                if ticket:
                    tickets[trade_id] = ticket
            else:
                ticket = tickets.get(trade_id)
                if ticket:
                    backend.close_position(
                        ticket,
                        trade.get("reason", "EXIT"),
                        close_price=float(trade["exit_price"]),
                        timestamp=timestamp,
                    )
                    closed += 1
                    if args.limit_trades and closed >= args.limit_trades:
                        break
    finally:
        backend.disconnect()

    print(json.dumps(backend.summary(), indent=2))
    return 0


def _submit_from_trade(backend: Mt5DemoExecutionBackend, trade: dict, timestamp) -> str | None:
    risk_mode = RiskMode(trade["risk_mode_at_entry"])
    base_fraction = RISK_PROFILES[risk_mode].risk_per_trade_fraction
    risk_fraction = base_fraction * float(trade.get("risk_scale", 1.0))
    if risk_fraction <= 0:
        return None
    try:
        volume = calculate_position_size(
            equity=backend.current_equity,
            risk_fraction=risk_fraction,
            entry_price=float(trade["entry_price"]),
            stop_price=float(trade["stop_loss"]),
            symbol=trade["symbol"],
        )
    except ValueError:
        return None
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
    return backend.submit_order(spec)


def _to_datetime(value) -> pd.Timestamp:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return pd.to_datetime(value).to_pydatetime()


if __name__ == "__main__":
    raise SystemExit(main())
