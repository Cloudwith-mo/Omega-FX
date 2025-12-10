"""Thin adapter to expose the MT5 backend via the adapters namespace."""

from __future__ import annotations

from core.execution_accounts import Mt5AccountConfig
from execution_backends.mt5_demo import Mt5DemoExecutionBackend, mt5


def initialize_mt5_terminal(account: Mt5AccountConfig | None = None) -> None:
    """Initialize MT5 and optionally log into the provided account."""
    init_kwargs: dict[str, object] = {}
    if account and account.login is not None:
        init_kwargs["login"] = account.login
        if account.password is not None:
            init_kwargs["password"] = account.password
        if account.server:
            init_kwargs["server"] = account.server
    try:
        initialized = mt5.initialize(**init_kwargs)
    except TypeError:
        initialized = mt5.initialize()
    if not initialized:
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    if account and account.login is not None:
        if not mt5.login(login=account.login, password=account.password, server=account.server):
            raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")


def shutdown_mt5_terminal() -> None:
    """Shutdown the MT5 terminal if loaded."""
    try:
        mt5.shutdown()
    except Exception:
        return None


__all__ = ["Mt5DemoExecutionBackend", "initialize_mt5_terminal", "shutdown_mt5_terminal", "mt5"]
