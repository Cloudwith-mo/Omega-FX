from __future__ import annotations

from datetime import datetime, timezone

_TIER_SHORT_MAP = {
    "conservative": "cons",
    "normal": "norm",
    "aggressive": "aggr",
}


def _shorten_tier(tier: str) -> str:
    resolved = (tier or "unknown").lower()
    if resolved in _TIER_SHORT_MAP:
        return _TIER_SHORT_MAP[resolved]
    return resolved.replace("-", "")[:6] or "custom"


def generate_session_id(
    env: str, tier: str, *, timestamp: datetime | None = None
) -> str:
    env_key = (env or "unknown").lower()
    tier_key = _shorten_tier(tier)
    ts = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{env_key}_{tier_key}_{ts}"
