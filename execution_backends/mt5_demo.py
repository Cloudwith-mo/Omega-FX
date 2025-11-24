"""Compatibility shim; MT5 backend now lives in adapters.mt5_backend."""

from __future__ import annotations

import adapters.mt5_backend as _backend

Mt5DemoExecutionBackend = _backend.Mt5DemoExecutionBackend
initialize_mt5_terminal = _backend.initialize_mt5_terminal
shutdown_mt5_terminal = _backend.shutdown_mt5_terminal
mt5 = _backend.mt5

__all__ = [
    "Mt5DemoExecutionBackend",
    "initialize_mt5_terminal",
    "shutdown_mt5_terminal",
    "mt5",
]
