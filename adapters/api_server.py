"""Lightweight FastAPI server factory for Omega FX telemetry."""

from __future__ import annotations

from typing import Any, Dict
from datetime import datetime


def get_api_app(extra_state: Dict[str, Any] | None = None):
    """
    Build a FastAPI app on demand.

    FastAPI is imported lazily so that the core package stays dependency-light.
    """

    try:
        from fastapi import FastAPI  # type: ignore
    except Exception as exc:  # pragma: no cover - guardrail for missing optional deps
        raise RuntimeError("FastAPI is not installed. pip install fastapi to run the API server.") from exc

    app = FastAPI(title="Omega FX API", version="0.1.0")
    state = extra_state or {}

    @app.get("/health")
    def healthcheck() -> dict:
        return {"status": "ok"}

    @app.get("/state")
    def state_snapshot() -> Dict[str, Any]:
        return state

    @app.get("/status")
    def status() -> Dict[str, Any]:
        return {
            "status": "ok",
            "bot_id": state.get("bot_id"),
            "mt5_account_alias": state.get("mt5_account"),
            "timestamp": datetime.utcnow().isoformat(),
        }

    return app
