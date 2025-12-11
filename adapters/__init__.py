"""Integration adapters for external services (MT5, APIs, chat)."""

from __future__ import annotations

from adapters.mt5_backend import Mt5DemoExecutionBackend
from execution_backends.simulated import SimulatedExecutionBackend

__all__ = ["Mt5DemoExecutionBackend", "SimulatedExecutionBackend"]
