#!/usr/bin/env python3
"""Local FastAPI server to expose OmegaFX status."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query

THIS_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.dirname(THIS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.monitoring_helpers import (  # noqa: E402
    DEFAULT_LOG_PATH,
    DEFAULT_SNAPSHOT_PATH,
    DEFAULT_SUMMARY_PATH,
    build_report_payload,
    build_status_payload,
)
from scripts.run_daily_exec_report import read_latest_session_id  # noqa: E402
from scripts.query_last_trades import load_trades  # noqa: E402

LOG_PATH = DEFAULT_LOG_PATH
SUMMARY_PATH = DEFAULT_SUMMARY_PATH
SNAPSHOT_PATH = DEFAULT_SNAPSHOT_PATH

app = FastAPI(title="OmegaFX Local API", version="1.0")


@app.get("/status")
def get_status(
    hours: float = Query(24.0, ge=0.0), include_historical: bool = Query(False)
) -> dict:
    return build_status_payload(
        hours=hours,
        log_path=LOG_PATH,
        summary_path=SUMMARY_PATH,
        snapshot_path=SNAPSHOT_PATH,
        include_historical=include_historical,
    )


@app.get("/trades")
def get_trades(
    hours: float = Query(24.0, ge=0.0),
    limit: int = Query(50, ge=1),
    session_id: str | None = None,
    include_historical: bool = Query(False),
) -> list[dict]:
    if not LOG_PATH.exists():
        raise HTTPException(status_code=404, detail="Execution log not found.")
    return load_trades(
        LOG_PATH,
        hours=hours,
        session_id=session_id,
        limit=limit,
        include_historical=include_historical,
    )


@app.get("/report")
def get_report(
    hours: float = Query(24.0, ge=0.0),
    session_id: str | None = None,
    use_latest_session: bool = False,
    include_historical: bool = Query(False),
) -> dict:
    target_session = session_id
    session_only = False
    if use_latest_session:
        target_session = target_session or read_latest_session_id(SUMMARY_PATH)
        session_only = bool(target_session)
    report = build_report_payload(
        hours=hours,
        log_path=LOG_PATH,
        summary_path=SUMMARY_PATH,
        session_id=target_session,
        session_only=session_only,
        include_historical=include_historical,
    )
    return report


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
