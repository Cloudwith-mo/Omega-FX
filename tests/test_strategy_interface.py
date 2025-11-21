from __future__ import annotations

import pandas as pd

from strategies.omega_m15 import OmegaM15Strategy


def test_omega_m15_required_features() -> None:
    strategy = OmegaM15Strategy()
    features = strategy.required_features()
    assert "M15_current" in features
    assert "M15_previous" in features
    assert "close" in features["M15_current"]


def test_omega_m15_on_bar_output() -> None:
    strategy = OmegaM15Strategy()
    current = pd.Series(
        {
            "close": 1.1000,
            "SMA_fast": 1.1010,
            "SMA_slow": 1.0990,
            "ATR_14": 0.0005,
        }
    )
    previous = pd.Series(
        {
            "close": 1.0995,
            "SMA_fast": 1.0980,
            "SMA_slow": 1.0990,
            "ATR_14": 0.0005,
        }
    )
    signal = strategy.on_bar(
        timestamp=pd.Timestamp("2024-01-01T00:15:00Z"),
        features_by_tf={
            "M15_current": current,
            "M15_previous": previous,
        },
    )
    assert signal["action"] in {"long", "short", "flat"}
    assert signal["risk_tier"] in {"A", "B", "UNKNOWN", "C"}
    assert isinstance(signal.get("meta", {}), dict)
