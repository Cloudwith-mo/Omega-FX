from __future__ import annotations

from core.bot_profiles import list_bot_profiles, load_bot_profile


def test_demo_bot_profiles_have_expected_strategies() -> None:
    available = list_bot_profiles()
    expected_bots = {
        "demo_trend_only": {"strategies": {"OMEGA_M15_TF1": 1.0}, "symbols": {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD"}},
        "demo_mr_only": {"strategies": {"OMEGA_MR_M15": 1.0}, "symbols": {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD"}},
        "demo_session_only": {
            "strategies": {"OMEGA_SESSION_LDN_M15": 1.0},
            "symbols": {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD"},
        },
        "demo_trend_mr_london": {
            "strategies": {"OMEGA_M15_TF1": 0.5, "OMEGA_MR_M15": 0.3, "OMEGA_SESSION_LDN_M15": 0.2},
            "symbols": {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD"},
        },
    }

    for bot_id, expectations in expected_bots.items():
        assert bot_id in available
        profile = load_bot_profile(bot_id)
        assert profile.bot_id == bot_id
        assert set(profile.symbols) == expectations["symbols"]
        assert profile.firm_profile.upper() == "PROP_EVAL"
        assert profile.mt5_account.startswith("DEMO_")
        assert profile.env == "demo"
        assert profile.risk_tier.lower() == "conservative"
        assert profile.strategy_risk_map == expectations["strategies"]
