"""MetaTrader5 demo execution backend."""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import MetaTrader5 as mt5  # type: ignore

from core.constants import DEFAULT_STRATEGY_ID
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
        session_id: str | None = None,
        risk_env: str | None = None,
        risk_tier: str | None = None,
        strategy_id: str | None = None,
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
        self.session_id = session_id or ""
        self.risk_env = (risk_env or "").lower()
        self.risk_tier = (risk_tier or "").lower()
        self.default_strategy_id = strategy_id or DEFAULT_STRATEGY_ID
        self.data_mode = "historical" if dry_run else "live"
        self.positions: Dict[str, ExecutionPosition] = {}
        self.current_equity = 0.0
        self.initial_equity = 0.0
        self.starting_equity = 0.0
        self.ending_equity = 0.0
        self.starting_balance = 0.0
        self.ending_balance = 0.0
        self.daily_start_equity = 0.0
        self.daily_realized = 0.0
        self.trade_records: list[dict] = []
        self.connected = False
        self.filter_counters: dict[str, int] = {"max_positions": 0, "daily_loss": 0, "invalid_stops": 0}
        self.last_limit_reason: str | None = None

    # ------------------------------------------------------------------ API ---

    def connect(self) -> None:
        if self.connected:
            return
        init_kwargs: dict[str, object] = {}
        if self.login is not None:
            # Pass credentials into initialize so headless terminals authorize correctly.
            init_kwargs["login"] = self.login
            if self.password is not None:
                init_kwargs["password"] = self.password
            if self.server is not None:
                init_kwargs["server"] = self.server
        try:
            initialized = mt5.initialize(**init_kwargs)
        except TypeError:
            # Older MetaTrader5 stubs (unit tests) may not accept keyword args; fall back to legacy call.
            initialized = mt5.initialize()
        if not initialized:
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        if self.login is not None:
            if not mt5.login(login=self.login, password=self.password, server=self.server):
                raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")
        info = mt5.account_info()
        if info is None:
            raise RuntimeError("MT5 account_info() returned None.")
        start_equity = float(getattr(info, 'equity', None) or getattr(info, 'balance', None) or 0.0)
        if start_equity <= 0:
            raise RuntimeError("MT5 account has non-positive equity.")
        self.initial_equity = start_equity
        self.starting_equity = start_equity
        self.current_equity = start_equity
        self.ending_equity = start_equity
        start_balance = float(getattr(info, 'balance', None) or start_equity)
        self.starting_balance = start_balance
        self.ending_balance = start_balance
        self.daily_start_equity = self.initial_equity
        self.daily_realized = 0.0
        self._ensure_log_header()
        self.connected = True

    def disconnect(self) -> None:
        if self.connected:
            info = mt5.account_info()
            if info is not None:
                ending_equity = float(getattr(info, 'equity', None) or self.current_equity)
                ending_balance = float(getattr(info, 'balance', None) or ending_equity)
                self.ending_equity = ending_equity
                self.ending_balance = ending_balance
                self.current_equity = ending_equity
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

    def submit_order(self, order: OrderSpec) -> str | None:
        self._ensure_ready()
        if order.stop_loss is None:
            raise RuntimeError("MT5 backend requires stop-loss price.")
        historical_entry = float(order.entry_price or self._current_price(order.symbol, order.direction))
        entry_price = historical_entry
        stop_loss = float(order.stop_loss)
        take_profit = float(order.take_profit) if order.take_profit is not None else None
        if not self.dry_run:
            entry_price, stop_loss, take_profit = self._realign_live_prices(
                order, historical_entry, stop_loss, take_profit
            )
        risk_amount = self._risk_amount(order.symbol, entry_price, stop_loss, order.volume)
        self.last_limit_reason = None
        max_risk = self.per_trade_risk_fraction * self.daily_start_equity
        if risk_amount > max_risk:
            raise RuntimeError("Per-trade risk limit exceeded.")
        limit_reason = self._limit_reason(risk_amount)
        if limit_reason:
            self._record_filtered_event(order, entry_price, stop_loss, take_profit, risk_amount, limit_reason)
            return None
        ticket = f"MT5-{uuid.uuid4().hex[:10]}"
        timestamp = order.timestamp or datetime.now(timezone.utc)
        if not self.dry_run:
            request = self._build_order_request(order, entry_price, stop_loss, take_profit)
            result = mt5.order_send(request)
            retcode = getattr(result, "retcode", None) if result is not None else None
            if retcode in (getattr(mt5, "TRADE_RETCODE_INVALID_STOPS", 10016), 10016):
                self._record_filtered_event(order, entry_price, stop_loss, take_profit, risk_amount, "invalid_stops")
                return None
            if result is None or retcode != mt5.TRADE_RETCODE_DONE:
                last_error = mt5.last_error()
                raise RuntimeError(f"MT5 order_send failed: {result} (last_error={last_error})")
            ticket = str(getattr(result, "order", ticket))
        position = ExecutionPosition(
            ticket=ticket,
            symbol=order.symbol.upper(),
            direction=order.direction,
            volume=order.volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            opened_at=timestamp,
            tag=order.tag,
            max_loss_amount=risk_amount,
            signal_reason=str(order.metadata.get("signal_reason") or order.tag),
            strategy_id=order.strategy_id or self.default_strategy_id,
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
                raise RuntimeError(f"Failed to close {ticket}: {result} (last_error={mt5.last_error()})")
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
                "signal_reason": position.signal_reason,
                "strategy_id": position.strategy_id,
            }
        )
        self._log_event(event_time, "CLOSE", position, exit_price, reason)

    # -------------------------------------------------------------- Internals ---

    def _ensure_ready(self) -> None:
        if not self.connected:
            raise RuntimeError("MT5 backend not connected.")

    def _limit_reason(self, risk_amount: float) -> str | None:
        if len(self.positions) >= self.max_positions:
            return "max_positions"
        worst_case_loss = max(0.0, -self.daily_realized)
        for pos in self.positions.values():
            worst_case_loss += pos.max_loss_amount
        projected = worst_case_loss + risk_amount
        if projected > (self.daily_loss_fraction * self.daily_start_equity):
            return "daily_loss"
        return None

    def _realign_live_prices(
        self,
        order: OrderSpec,
        historical_entry: float,
        stop_loss: float,
        take_profit: float | None,
    ) -> tuple[float, float, float | None]:
        live_entry = self._current_price(order.symbol, order.direction)
        stop_offset = stop_loss - historical_entry
        take_profit_offset = take_profit - historical_entry if take_profit is not None else None
        adjusted_stop = live_entry + stop_offset
        adjusted_tp = live_entry + take_profit_offset if take_profit_offset is not None else None
        adjusted_stop, adjusted_tp = self._respect_min_stop_distance(
            order.symbol,
            order.direction,
            live_entry,
            adjusted_stop,
            adjusted_tp,
        )
        return live_entry, adjusted_stop, adjusted_tp

    def _respect_min_stop_distance(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float | None,
    ) -> tuple[float, float | None]:
        min_distance = self._min_stop_distance(symbol)
        buffer = max(min_distance, 1e-6)
        if direction == "long":
            if stop_loss >= entry_price - buffer:
                stop_loss = entry_price - buffer
            if min_distance > 0 and (entry_price - stop_loss) < min_distance:
                stop_loss = entry_price - min_distance
            stop_loss = max(0.0, stop_loss)
            if take_profit is not None:
                if take_profit <= entry_price + buffer:
                    take_profit = entry_price + buffer
                if min_distance > 0 and (take_profit - entry_price) < min_distance:
                    take_profit = entry_price + min_distance
        else:
            if stop_loss <= entry_price + buffer:
                stop_loss = entry_price + buffer
            if min_distance > 0 and (stop_loss - entry_price) < min_distance:
                stop_loss = entry_price + min_distance
            if take_profit is not None:
                if take_profit >= entry_price - buffer:
                    take_profit = entry_price - buffer
                if min_distance > 0 and (entry_price - take_profit) < min_distance:
                    take_profit = entry_price - min_distance
                take_profit = max(0.0, take_profit)
        return stop_loss, take_profit

    def _min_stop_distance(self, symbol: str) -> float:
        info = mt5.symbol_info(symbol)
        if info is None:
            return 0.0
        point = float(getattr(info, "point", 0.0) or 0.0)
        level = float(getattr(info, "trade_stops_level", 0.0) or 0.0)
        return point * level

    def _record_filtered_event(
        self,
        order: OrderSpec,
        entry_price: float,
        stop_loss: float,
        take_profit: float | None,
        risk_amount: float,
        reason: str,
    ) -> None:
        self.last_limit_reason = reason
        self.filter_counters[reason] = self.filter_counters.get(reason, 0) + 1
        timestamp = order.timestamp or datetime.now(timezone.utc)
        pseudo_position = ExecutionPosition(
            ticket=f"FILTER-{reason}-{uuid.uuid4().hex[:8]}",
            symbol=order.symbol.upper(),
            direction=order.direction,
            volume=order.volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            opened_at=timestamp,
            tag=order.tag,
            max_loss_amount=risk_amount,
            signal_reason=str(order.metadata.get("signal_reason") or order.tag),
            strategy_id=order.strategy_id or self.default_strategy_id,
        )
        self._log_event(timestamp, "FILTER", pseudo_position, entry_price, reason)

    def _risk_amount(self, symbol: str, entry: float, stop: float, volume: float) -> float:
        meta = get_symbol_meta(symbol)
        pip_distance = abs(entry - stop) / meta.pip_size
        return pip_distance * meta.pip_value_per_standard_lot * volume

    def _current_price(self, symbol: str, direction: str | None = None) -> float:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"MT5 symbol_info_tick returned None for {symbol}")
        price = None
        if direction == "long":
            price = getattr(tick, "ask", None)
        elif direction == "short":
            price = getattr(tick, "bid", None)
        if price is None:
            price = getattr(tick, "bid", None) or getattr(tick, "ask", None)
        if price is None:
            raise RuntimeError("MT5 tick data missing bid/ask.")
        return float(price)

    def _build_order_request(
        self,
        order: OrderSpec,
        price: float,
        stop_loss: float,
        take_profit: float | None,
    ) -> dict:
        order_type = mt5.ORDER_TYPE_BUY if order.direction == "long" else mt5.ORDER_TYPE_SELL
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": order.volume,
            "type": order_type,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": 10,
            "magic": 0,
            "comment": self._build_comment(order.tag),
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
            "comment": self._build_comment("CLOSE"),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

    def _build_comment(self, default_tag: str) -> str:
        if not self.session_id:
            return default_tag
        comment = self.session_id
        if len(comment) > 29:
            return comment[:29]
        return comment

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
        header = (
            "timestamp,event,session_id,strategy_id,ticket,symbol,direction,volume,price,reason,signal_reason,equity,data_mode\\n"
        )
        with self.log_path.open("a", encoding="utf-8") as fh:
            if not file_exists:
                fh.write(header)
            session_value = self.session_id or ""
            signal_value = getattr(position, "signal_reason", "")
            fh.write(
                f"{timestamp.isoformat()},{event},{session_value},{position.strategy_id},{position.ticket},{position.symbol},"
                f"{position.direction},{position.volume:.2f},{price:.5f},{reason},{signal_value},{self.current_equity:.2f},{self.data_mode}\n"
            )

    def _ensure_log_header(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        columns = [
            "timestamp",
            "event",
            "session_id",
            "strategy_id",
            "ticket",
            "symbol",
            "direction",
            "volume",
            "price",
            "reason",
            "signal_reason",
            "equity",
            "data_mode",
        ]
        header_line = ",".join(columns)
        if not self.log_path.exists():
            self.log_path.write_text(header_line + "\n")
            return
        with self.log_path.open("r", encoding="utf-8", newline="") as fh:
            dict_reader = csv.DictReader(fh)
            rows = list(dict_reader)
            existing_cols = dict_reader.fieldnames or []
        if not existing_cols:
            self.log_path.write_text(header_line + "\n")
            return
        normalized = [col.strip() for col in existing_cols]
        if normalized == columns:
            return
        with self.log_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                strategy_value = row.get("strategy_id") or row.get("strategy_tag") or DEFAULT_STRATEGY_ID
                writer.writerow({
                    "timestamp": row.get("timestamp", ""),
                    "event": row.get("event", ""),
                    "session_id": row.get("session_id", ""),
                    "strategy_id": strategy_value,
                    "ticket": row.get("ticket", ""),
                    "symbol": row.get("symbol", ""),
                    "direction": row.get("direction", ""),
                    "volume": row.get("volume", ""),
                    "price": row.get("price", ""),
                    "reason": row.get("reason", ""),
                    "signal_reason": row.get("signal_reason", ""),
                    "equity": row.get("equity", ""),
                    "data_mode": row.get("data_mode", "live"),
                })
    def save_summary(self) -> None:
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.write_text(json.dumps(self.summary(), indent=2))

    def summary(self) -> dict:
        strategy_stats = self._compute_strategy_stats()
        wins = sum(1 for trade in self.trade_records if trade["pnl"] > 0)
        total = len(self.trade_records)
        daily_loss = max(0.0, -self.daily_realized)
        signal_counts: dict[str, int] = {}
        for trade in self.trade_records:
            label = str(trade.get("signal_reason") or "unknown")
            signal_counts[label] = signal_counts.get(label, 0) + 1
        return {
            "dry_run": self.dry_run,
            "initial_equity": self.initial_equity,
            "final_equity": self.current_equity,
            "starting_equity": self.starting_equity,
            "ending_equity": self.ending_equity or self.current_equity,
            "session_start_equity": self.starting_equity or self.initial_equity,
            "session_end_equity": self.ending_equity or self.current_equity,
            "starting_balance": self.starting_balance,
            "ending_balance": self.ending_balance or self.starting_balance,
            "number_of_trades": total,
            "win_rate": wins / total if total else 0.0,
            "max_open_positions": self.max_positions,
            "per_trade_risk_fraction": self.per_trade_risk_fraction,
            "daily_loss_fraction": self.daily_loss_fraction,
            "daily_realized_loss": daily_loss,
            "filtered_max_positions": self.filter_counters.get("max_positions", 0),
            "risk_env": self.risk_env,
            "session_id": self.session_id,
            "strategy_id": self.default_strategy_id,
            "filtered_daily_loss": self.filter_counters.get("daily_loss", 0),
            "filtered_invalid_stops": self.filter_counters.get("invalid_stops", 0),
            "signal_reason_counts": signal_counts,
            "session_pnl": (self.ending_equity or self.current_equity) - (self.starting_equity or self.initial_equity),
            "session_balance_pnl": (self.ending_balance or self.starting_balance) - self.starting_balance,
            "per_strategy": strategy_stats,
        }

    def _compute_strategy_stats(self) -> dict[str, dict]:
        stats: dict[str, dict] = {}
        for trade in self.trade_records:
            strategy_id = trade.get("strategy_id") or self.default_strategy_id
            entry = stats.setdefault(strategy_id, {"trades": 0, "wins": 0, "pnl": 0.0})
            entry["trades"] += 1
            pnl_value = float(trade.get("pnl", 0.0) or 0.0)
            entry["pnl"] += pnl_value
            if pnl_value > 0:
                entry["wins"] += 1
        for entry in stats.values():
            trades = entry["trades"]
            wins = entry.pop("wins")
            entry["win_rate"] = (wins / trades) if trades else 0.0
            entry["avg_pnl_per_trade"] = (entry["pnl"] / trades) if trades else 0.0
        return stats

