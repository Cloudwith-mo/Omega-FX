from __future__ import annotations

from typing import Any, Dict

try:
    import MetaTrader5 as mt5  # type: ignore
except ImportError:  # pragma: no cover - optional dependency in CI
    mt5 = None


MISSING_MT5_ERROR = "MetaTrader5 module unavailable"


def fetch_open_positions_snapshot() -> Dict[str, Any]:
    """Return a snapshot of currently open MT5 positions."""
    snapshot: Dict[str, Any] = {
        "count": 0,
        "total_pnl": 0.0,
        "error": None,
        "connected": False,
    }
    if mt5 is None:
        snapshot["error"] = MISSING_MT5_ERROR
        return snapshot

    initialized = False
    try:
        if not mt5.initialize():
            snapshot["error"] = f"MT5 init failed: {mt5.last_error()}"
            return snapshot
        initialized = True
        positions = mt5.positions_get()
        if positions is None:
            snapshot["error"] = f"positions_get failed: {mt5.last_error()}"
            return snapshot
        snapshot["connected"] = True
        snapshot["count"] = len(positions)
        snapshot["total_pnl"] = sum(float(getattr(pos, "profit", 0.0) or 0.0) for pos in positions)
        return snapshot
    except Exception as exc:  # pragma: no cover - MT5 runtime errors
        snapshot["error"] = str(exc)
        return snapshot
    finally:
        if initialized:
            mt5.shutdown()
