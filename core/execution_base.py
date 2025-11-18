"""Strategy-agnostic execution interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class OrderSpec:
    """Normalized order request produced by a strategy or signal router."""

    symbol: str
    direction: str  # "long" or "short"
    volume: float  # MT5 lots
    entry_type: str = "market"
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timestamp: Optional[datetime] = None
    tag: str = "OMEGA_FX"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPosition:
    """Tracked live position for execution backends."""

    ticket: str
    symbol: str
    direction: str
    volume: float
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    opened_at: datetime
    tag: str
    max_loss_amount: float = 0.0


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
    def sync_positions(self) -> List[ExecutionPosition]:
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
        close_price: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Close an existing position."""
