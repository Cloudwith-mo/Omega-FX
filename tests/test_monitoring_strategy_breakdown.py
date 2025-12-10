from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.monitoring_helpers import build_report_payload, build_status_payload


def _write_log(path: Path, session_id: str) -> None:
    now = datetime.now(timezone.utc) - timedelta(minutes=30)
    header = "timestamp,event,session_id,strategy_id,ticket,symbol,direction,volume,price,reason,signal_reason,equity,data_mode"
    rows = []
    entries = [
        ("OMEGA_M15_TF1", "long", 1.1050, 1.1060),
        ("OMEGA_MR_M15", "short", 1.2050, 1.2000),
        ("OMEGA_SESSION_LDN_M15", "long", 1.3050, 1.3080),
    ]
    for idx, (strategy_id, direction, entry_price, exit_price) in enumerate(entries):
        open_time = now + timedelta(minutes=idx * 2)
        close_time = open_time + timedelta(minutes=1)
        ticket = f"T{idx}"
        rows.append(
            f"{open_time.isoformat()},OPEN,{session_id},{strategy_id},{ticket},EURUSD,{direction},0.10,{entry_price},signal,reason,{100000 + idx},live"
        )
        rows.append(
            f"{close_time.isoformat()},CLOSE,{session_id},{strategy_id},{ticket},EURUSD,{direction},0.10,{exit_price},Exit,reason,{100005 + idx},live"
        )
    path.write_text(header + "\n" + "\n".join(rows), encoding="utf-8")


def _write_summary(path: Path, session_id: str) -> None:
    data = {
        "session_id": session_id,
        "risk_env": "demo",
        "per_strategy": {
            "OMEGA_M15_TF1": {"trades": 2, "wins": 1, "losses": 1, "pnl": 50},
            "OMEGA_MR_M15": {"trades": 1, "wins": 1, "losses": 0, "pnl": 25},
            "OMEGA_SESSION_LDN_M15": {"trades": 1, "wins": 1, "losses": 0, "pnl": 35},
        },
    }
    path.write_text(__import__("json").dumps(data))


def test_strategy_breakdown_lists(tmp_path: Path) -> None:
    session_id = "demo_test"
    log_path = tmp_path / "log.csv"
    summary_path = tmp_path / "summary.json"
    _write_log(log_path, session_id)
    _write_summary(summary_path, session_id)

    status_payload = build_status_payload(
        hours=24.0,
        log_path=log_path,
        summary_path=summary_path,
        include_historical=True,
    )
    latest = status_payload.get("strategy_breakdown_latest")
    report_block = status_payload.get("strategy_breakdown_report")
    assert latest and len(latest) == 3
    assert report_block and len(report_block) == 3

    report_payload = build_report_payload(
        hours=24.0,
        log_path=log_path,
        summary_path=summary_path,
        include_historical=True,
    )
    report_breakdown = report_payload.get("strategy_breakdown_report")
    assert report_breakdown and len(report_breakdown) == 3
