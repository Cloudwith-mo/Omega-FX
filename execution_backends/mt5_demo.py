"""MetaTrader5 demo execution backend."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import MetaTrader5 as mt5  # type: ignore

from core.execution_base import ExecutionBackend, ExecutionPosition, OrderSpec
from core.position_sizing import get_symbol_meta


class Mt5DemoExecutionBackend(ExecutionBackend):
    """Execution backend that routes orders to a MetaTrader5 demo account."""

    def __init__(
        self,
        *,
        login: int | None,
        password: str | None,
        server: str | None,
        dry_run: bool = True,
        max_positions: int = 2,
        per_trade_risk_fraction: float = 0.004,
        daily_loss_fraction: float = 0.02,
        log_path: str | Path = "results/mt5_demo_exec_log.csv",
        summary_path: str | Path = "results/mt5_demo_exec_summary.json",
    ) -> None:
        self.login = login
        self.password = password
        self.server = server
        self.dry_run = dry_run
        self.max_positions = max_positions
        self.per_trade_risk_fraction = per_trade_risk_fraction
        self.daily_loss_fraction = daily_loss_fraction
        self.log_path = Path(log_path)
        self.summary_path = Path(summary_path)
        self.positions: Dict[str, ExecutionPosition] = {}
        self.current_equity = 0.0
        self.initial_equity = 0.0
        self.daily_start_equity = 0.0
        self.daily_realized = 0.0
        self.trade_records: list[dict] = []
        self.connected = False

    # ------------------------------------------------------------------ API ---

    def connect(self) -> None:
        if self.connected:
            return
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        if self.login is not None:
            if not mt5.login(login=self.login, password=self.password, server=self.server):
                raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")
        info = mt5.account_info()
        if info is None:
            raise RuntimeError("MT5 account_info() returned None.")
        self.initial_equity = float(info.equity or info.balance or 0.0)
        if self.initial_equity <= 0:
            raise RuntimeError("MT5 account has non-positive equity.")
        self.current_equity = self.initial_equity
        self.daily_start_equity = self.initial_equity
        self.daily_realized = 0.0
        self._ensure_log_header()
        self.connected = True

    def disconnect(self) -> None:
        if self.connected:
            mt5.shutdown()
        self.connected = False
        self.save_summary()

    def sync_positions(self):
        mt5_positions = mt5.positions_get()
        synced: list[ExecutionPosition] = []
        for pos in mt5_positions or []:
            synced.append(
                ExecutionPosition(
                    ticket=str(getattr(pos, "ticket", "")),
                    symbol=str(getattr(pos, "symbol", "")),
                    direction="long" if getattr(pos, "type", 0) in (mt5.ORDER_TYPE_BUY,) else "short",
                    volume=float(getattr(pos, "volume", 0.0)),
                    entry_price=float(getattr(pos, "price_open", 0.0)),
                    stop_loss=float(getattr(pos, "sl", 0.0)) or None,
                    take_profit=float(getattr(pos, "tp", 0.0)) or None,
                    opened_at=datetime.utcfromtimestamp(getattr(pos, "time", 0)),
                    tag="MT5",
                    max_loss_amount=0.0,
                )
            )
        return synced

    def submit_order(self, order: OrderSpec) -> str:
        self._ensure_ready()
        self._enforce_limits(order)
        entry_price = float(order.entry_price or self._current_price(order.symbol))
        stop_loss = order.stop_loss
        if stop_loss is None:
            raise RuntimeError("MT5 backend requires stop loss for every order.")
        risk_amount = self._risk_amount(order.symbol, entry_price, stop_loss, order.volume)
        ticket = f"MT5-{uuid.uuid4().hex[:10]}"
        timestamp = order.timestamp or datetime.now(timezone.utc)
        if not self.dry_run:
            request = self._build_order_request(order, entry_price, stop_loss)
            result = mt5.order_send(request)
            if result is None or getattr(result, "retcode", None) != mt5.TRADE_RETCODE_DONE:
                raise RuntimeError(f"MT5 order_send failed: {result}")
            ticket = str(getattr(result, "order", ticket))
        position = ExecutionPosition(
            ticket=ticket,
            symbol=order.symbol.upper(),
            direction=order.direction,
            volume=order.volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=order.take_profit,
            opened_at=timestamp,
            tag=order.tag,
            max_loss_amount=risk_amount,
        )
        self.positions[ticket] = position
        self._log_event(timestamp, "OPEN", position, entry_price, order.tag)
        return ticket

    def close_position(
        self,
        ticket: str,
        reason: str,
        *,
        close_price: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        self._ensure_ready()
        position = self.positions.pop(ticket, None)
        if position is None:
            raise KeyError(f"Unknown ticket {ticket}")
        exit_price = float(close_price or position.entry_price)
        if not self.dry_run:
            close_request = self._build_close_request(position, exit_price)
            result = mt5.order_send(close_request)
            if result is None or getattr(result, "retcode", None) != mt5.TRADE_RETCODE_DONE:
                raise RuntimeError(f"Failed to close {ticket}: {result}")
        pnl = self._pnl_for_position(position, exit_price)
        self.current_equity += pnl
        if pnl < 0:
            self.daily_realized += pnl
        event_time = timestamp or datetime.now(timezone.utc)
        self.trade_records.append(
            {
                "ticket": ticket,
                "symbol": position.symbol,
                "direction": position.direction,
                "volume": position.volume,
                "entry_price": position.entry_price,
                "exit_price": exit_price,
                "opened_at": position.opened_at.isoformat(),
                "closed_at": event_time.isoformat(),
                "reason": reason,
                "pnl": pnl,
            }
        )
        self._log_event(event_time, "CLOSE", position, exit_price, reason)

    # -------------------------------------------------------------- Internals ---

    def _ensure_ready(self) -> None:
        if not self.connected:
            raise RuntimeError("MT5 backend not connected.")

    def _enforce_limits(self, order: OrderSpec) -> None:
        if len(self.positions) >= self.max_positions:
            raise RuntimeError("Max open positions exceeded.")
        if order.stop_loss is None or order.entry_price is None:
            raise RuntimeError("Orders must include entry and stop-loss prices.")
        risk_amount = self._risk_amount(order.symbol, order.entry_price, order.stop_loss, order.volume)
        max_risk = self.per_trade_risk_fraction * self.daily_start_equity
        if risk_amount > max_risk:
            raise RuntimeError("Per-trade risk limit exceeded.")
        worst_case_loss = max(0.0, -self.daily_realized)
        for pos in self.positions.values():
            worst_case_loss += pos.max_loss_amount
        projected = worst_case_loss + risk_amount
        if projected > (self.daily_loss_fraction * self.daily_start_equity):
            raise RuntimeError("Daily loss limit breached.")

    def _risk_amount(self, symbol: str, entry: float, stop: float, volume: float) -> float:
        meta = get_symbol_meta(symbol)
        pip_distance = abs(entry - stop) / meta.pip_size
        return pip_distance * meta.pip_value_per_standard_lot * volume

    def _current_price(self, symbol: str) -> float:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"MT5 symbol_info_tick returned None for {symbol}")
        price = getattr(tick, "bid", None) or getattr(tick, "ask", None)
        if price is None:
            raise RuntimeError("MT5 tick data missing bid/ask.")
        return float(price)

    def _build_order_request(self, order: OrderSpec, price: float, stop_loss: float) -> dict:
        order_type = mt5.ORDER_TYPE_BUY if order.direction == "long" else mt5.ORDER_TYPE_SELL
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": order.volume,
            "type": order_type,
            "price": price,
            "sl": stop_loss,
            "tp": order.take_profit,
            "deviation": 10,
            "magic": 0,
            "comment": order.tag,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

    def _build_close_request(self, position: ExecutionPosition, price: float) -> dict:
        order_type = mt5.ORDER_TYPE_SELL if position.direction == "long" else mt5.ORDER_TYPE_BUY
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": int(self._safe_int(position.ticket)),
            "price": price,
            "deviation": 20,
            "magic": 0,
            "comment": "CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

    def _safe_int(self, ticket: str) -> int:
        try:
            return int(ticket)
        except (TypeError, ValueError):
            return 0

    def _pnl_for_position(self, position: ExecutionPosition, exit_price: float) -> float:
        meta = get_symbol_meta(position.symbol)
        pip_distance = (exit_price - position.entry_price) / meta.pip_size
        if position.direction == "short":
            pip_distance = -pip_distance
        return pip_distance * meta.pip_value_per_standard_lot * position.volume

    def _log_event(self, timestamp: datetime, event: str, position: ExecutionPosition, price: float, reason: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.log_path.exists()
        with self.log_path.open("a", encoding="utf-8") as fh:
            if not file_exists:
                fh.write("timestamp,event,ticket,symbol,direction,volume,price,reason,equity\n")
            fh.write(
                f"{timestamp.isoformat()},{event},{position.ticket},{position.symbol},"
                f"{position.direction},{position.volume:.2f},{price:.5f},{reason},{self.current_equity:.2f}\n"
            )

    def _ensure_log_header(self) -> None:
        if self.log_path.exists():
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("timestamp,event,ticket,symbol,direction,volume,price,reason,equity\n")

    # --------------------------------------------------------------- Summary ---

    def save_summary(self) -> None:
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.write_text(json.dumps(self.summary(), indent=2))

    def summary(self) -> dict:
        wins = sum(1 for trade in self.trade_records if trade["pnl"] > 0)
        total = len(self.trade_records)
        daily_loss = max(0.0, -self.daily_realized)
        return {
            "dry_run": self.dry_run,
            "initial_equity": self.initial_equity,
            "final_equity": self.current_equity,
            "number_of_trades": total,
            "win_rate": wins / total if total else 0.0,
            "max_open_positions": self.max_positions,
            "per_trade_risk_fraction": self.per_trade_risk_fraction,
            "daily_loss_fraction": self.daily_loss_fraction,
            "daily_realized_loss": daily_loss,
        }
