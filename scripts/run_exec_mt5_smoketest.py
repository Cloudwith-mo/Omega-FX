#!/usr/bin/env python3
"""Quick sanity check for MT5 demo connectivity."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
import MetaTrader5 as mt5
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.execution_accounts import available_profile_names, resolve_account_config  # noqa: E402
from core.execution_base import OrderSpec  # noqa: E402
from core.position_sizing import calculate_position_size, get_symbol_meta  # noqa: E402
from execution_backends.mt5_demo import Mt5DemoExecutionBackend  # noqa: E402


def parse_args() -> argparse.Namespace:
    choices = available_profile_names()
    parser = argparse.ArgumentParser(description="MT5 demo smoke test.")
    parser.add_argument("--account_profile", choices=choices if choices else None, required=True)
    parser.add_argument(
        "--dry_run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use --no-dry_run to actually send orders.",
    )
    parser.add_argument("--login", type=int, default=None)
    parser.add_argument("--server", type=str, default=None)
    parser.add_argument("--password", type=str, default=None)
    parser.add_argument("--max_positions", type=int, default=1)
    parser.add_argument("--per_trade_risk_fraction", type=float, default=0.0005)
    parser.add_argument("--daily_loss_fraction", type=float, default=0.005)
    parser.add_argument("--risk_amount", type=float, default=5.0, help="Dollar risk for the smoke trade.")
    parser.add_argument("--stop_pips", type=float, default=10.0)
    parser.add_argument("--hold_seconds", type=float, default=2.0)
    parser.add_argument(
        "--summary_path",
        type=Path,
        default=Path("results/mt5_demo_smoketest_summary.json"),
        help="Where to write the summary JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    account = resolve_account_config(
        args.account_profile,
        login=args.login,
        password=args.password,
        server=args.server,
    )
    summary = perform_smoketest(account, args)
    args.summary_path.parent.mkdir(parents=True, exist_ok=True)
    args.summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


def perform_smoketest(account, args: argparse.Namespace, backend_cls=Mt5DemoExecutionBackend) -> dict:
    backend = backend_cls(
        login=account.login,
        password=account.password,
        server=account.server,
        dry_run=args.dry_run,
        max_positions=args.max_positions,
        per_trade_risk_fraction=args.per_trade_risk_fraction,
        daily_loss_fraction=args.daily_loss_fraction,
        log_path=Path("results/mt5_demo_exec_log.csv"),
        summary_path=Path("results/mt5_demo_exec_summary.json"),
    )
    summary = {
        "account_profile": account.name,
        "dry_run": args.dry_run,
        "connected": False,
        "order_sent": False,
        "order_closed": False,
        "error": None,
    }
    symbol = account.default_symbol or "EURUSD"
    try:
        backend.connect()
        summary["connected"] = True
        entry_price = _current_price(symbol)
        meta = get_symbol_meta(symbol)
        stop_distance = args.stop_pips * meta.pip_size
        stop_loss = entry_price - stop_distance
        risk_fraction = args.risk_amount / backend.initial_equity if backend.initial_equity else 0.0001
        volume = calculate_position_size(
            equity=backend.initial_equity,
            risk_fraction=max(risk_fraction, 1e-6),
            entry_price=entry_price,
            stop_price=stop_loss,
            symbol=symbol,
        )
        order = OrderSpec(
            symbol=symbol,
            direction="long",
            volume=volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=entry_price + stop_distance,
            timestamp=pd.Timestamp.utcnow().to_pydatetime(),
            tag="SMOKE_TEST",
        )
        ticket = backend.submit_order(order)
        summary["order_sent"] = True
        if not args.dry_run:
            time.sleep(max(0.0, args.hold_seconds))
        backend.close_position(ticket, "SMOKE_TEST_EXIT", close_price=entry_price)
        summary["order_closed"] = True
    except Exception as exc:  # pragma: no cover - best effort logging
        summary["error"] = str(exc)
    finally:
        backend.disconnect()
    return summary


def _current_price(symbol: str) -> float:
    tick = mt5.symbol_info_tick(symbol)
    if tick and getattr(tick, "bid", None):
        return float(tick.bid)
    if tick and getattr(tick, "ask", None):
        return float(tick.ask)
    return 1.0


if __name__ == "__main__":
    raise SystemExit(main())
