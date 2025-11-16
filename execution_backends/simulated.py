"""Offline execution backend used for replay tests."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from core.execution_base import ExecutionBackend, ExecutionPosition, OrderSpec
from core.position_sizing import get_symbol_meta


class SimulatedExecutionBackend(ExecutionBackend):
    """Simple backend that records fills to CSV and tracks equity."""

    def __init__(self, initial_equity: float, log_path: str | Path = "results/execution_sim_log.csv") -> None:
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.log_path = Path(log_path)
        self.positions: Dict[str, ExecutionPosition] = {}
        self.trade_records: List[dict] = []
        self.equity_history: List[Tuple[datetime, float]] = []
        self._connected = False

    def connect(self) -> None:
        if self._connected:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            with self.log_path.open("w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(
                    [
                        "timestamp",
                        "event",
                        "ticket",
                        "symbol",
                        "direction",
                        "volume",
                        "price",
                        "reason",
                        "equity",
                    ]
                )
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def sync_positions(self) -> List[ExecutionPosition]:
        return list(self.positions.values())

    def submit_order(self, order: OrderSpec) -> str:
        if order.volume <= 0:
            raise ValueError("Order volume must be positive for simulated execution.")
        timestamp = order.timestamp or datetime.utcnow()
        ticket = f"SIM-{uuid.uuid4().hex[:10]}"
        position = ExecutionPosition(
            ticket=ticket,
            symbol=order.symbol.upper(),
            direction=order.direction,
            volume=order.volume,
            entry_price=float(order.entry_price or 0.0),
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            opened_at=timestamp,
            tag=order.tag,
        )
        self.positions[ticket] = position
        self._write_row(timestamp, "OPEN", position, price=position.entry_price, reason=order.tag)
        return ticket

    def close_position(
        self,
        ticket: str,
        reason: str,
        *,
        close_price: float | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        position = self.positions.pop(ticket, None)
        if position is None:
            raise KeyError(f"Unknown ticket {ticket} for simulated backend.")
        exit_price = close_price if close_price is not None else position.entry_price
        meta = get_symbol_meta(position.symbol)
        pip_distance = (exit_price - position.entry_price) / meta.pip_size
        if position.direction == "short":
            pip_distance = -pip_distance
        pnl = pip_distance * meta.pip_value_per_standard_lot * position.volume
        self.current_equity += pnl
        event_time = timestamp or datetime.utcnow()
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
        self.equity_history.append((event_time, self.current_equity))
        self._write_row(event_time, "CLOSE", position, price=exit_price, reason=reason)

    # Helpers -----------------------------------------------------------------

    def _write_row(
        self,
        timestamp: datetime,
        event: str,
        position: ExecutionPosition,
        *,
        price: float,
        reason: str,
    ) -> None:
        with self.log_path.open("a", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    timestamp.isoformat(),
                    event,
                    position.ticket,
                    position.symbol,
                    position.direction,
                    f"{position.volume:.2f}",
                    f"{price:.5f}",
                    reason,
                    f"{self.current_equity:.2f}",
                ]
            )

    def max_drawdown_fraction(self) -> float:
        if not self.equity_history:
            return 0.0
        peak = self.initial_equity
        max_dd = 0.0
        for _, value in self.equity_history:
            if value > peak:
                peak = value
            if peak > 0:
                max_dd = max(max_dd, (peak - value) / peak)
        return max_dd

    def max_daily_loss_fraction(self) -> float:
        if not self.equity_history:
            return 0.0
        records = sorted(self.equity_history, key=lambda row: row[0])
        daily_start = self.initial_equity
        current_day = records[0][0].date()
        worst = 0.0
        equity_prev = self.initial_equity
        for timestamp, equity in records:
            day = timestamp.date()
            if day != current_day:
                if daily_start > 0:
                    worst = max(worst, max(0.0, (daily_start - equity_prev) / daily_start))
                daily_start = equity_prev
                current_day = day
            equity_prev = equity
        if daily_start > 0:
            worst = max(worst, max(0.0, (daily_start - equity_prev) / daily_start))
        return worst

    def summary(self) -> dict:
        total_pnl = self.current_equity - self.initial_equity
        wins = sum(1 for trade in self.trade_records if trade["pnl"] > 0)
        losses = sum(1 for trade in self.trade_records if trade["pnl"] <= 0)
        total = len(self.trade_records)
        win_rate = wins / total if total else 0.0
        return {
            "initial_equity": self.initial_equity,
            "final_equity": self.current_equity,
            "total_pnl": total_pnl,
            "number_of_trades": total,
            "win_rate": win_rate,
            "max_drawdown_fraction": self.max_drawdown_fraction(),
            "max_daily_loss_fraction": self.max_daily_loss_fraction(),
        }
