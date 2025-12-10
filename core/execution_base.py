"""Strategy-agnostic execution interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.constants import DEFAULT_STRATEGY_ID


@dataclass
class OrderSpec:
    """Normalized order request produced by a strategy or signal router."""

    symbol: str
    direction: str  # "long" or "short"
    volume: float  # MT5 lots
    entry_type: str = "market"
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    timestamp: datetime | None = None
    tag: str = "OMEGA_FX"
    metadata: dict[str, Any] = field(default_factory=dict)
    strategy_id: str = DEFAULT_STRATEGY_ID


@dataclass
class ExecutionPosition:
    """Tracked live position for execution backends."""

    ticket: str
    symbol: str
    direction: str
    volume: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    opened_at: datetime
    tag: str
    max_loss_amount: float = 0.0
    signal_reason: str = ""
    strategy_id: str = DEFAULT_STRATEGY_ID


class ExecutionBackend(ABC):
    """Abstract execution provider."""

    last_limit_reason: str | None = None

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to downstream execution venue."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close any resources associated with the backend."""

    @abstractmethod
    def sync_positions(self) -> list[ExecutionPosition]:
        """Return the list of open positions known to the backend."""

    @abstractmethod
    def submit_order(self, order: OrderSpec) -> str | None:
        """Submit a new order and return a ticket identifier. Returns None if filtered."""

    @abstractmethod
    def close_position(
        self,
        ticket: str,
        reason: str,
        *,
        close_price: float | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Close an existing position."""
