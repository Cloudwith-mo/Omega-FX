"""Utilities for loading MT5 execution account profiles."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import yaml

DEFAULT_CONFIG_PATH = Path("config/mt5_accounts.yaml")
DEFAULT_EXAMPLE_PATH = Path("config/mt5_accounts.example.yaml")


@dataclass(frozen=True)
class Mt5AccountConfig:
    name: str
    server: str | None
    login: int | None
    password: str | None
    description: str = ""
    default_symbol: str = "EURUSD"
    terminal_path: str | None = None


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_account_profiles(
    config_path: Path | None = None,
    example_path: Path | None = None,
) -> Dict[str, dict]:
    """Load MT5 profile definitions from yaml files."""

    base_path = config_path or DEFAULT_CONFIG_PATH
    fallback_path = example_path or DEFAULT_EXAMPLE_PATH

    merged: dict = {}
    fallback = _load_yaml(fallback_path).get("profiles", {})
    user_profiles = _load_yaml(base_path).get("profiles", {})

    for name, cfg in fallback.items():
        merged[name.upper()] = dict(cfg)
    for name, cfg in user_profiles.items():
        upper = name.upper()
        merged.setdefault(upper, {})
        merged[upper].update(cfg or {})
    return merged


def resolve_account_config(
    profile_name: str | None,
    *,
    login: int | None = None,
    password: str | None = None,
    server: str | None = None,
    config_path: Path | None = None,
    example_path: Path | None = None,
) -> Mt5AccountConfig:
    profiles = load_account_profiles(config_path=config_path, example_path=example_path)
    profile_data = profiles.get(profile_name.upper()) if profile_name else None
    env_login = _maybe_int(os.environ.get("OMEGA_MT5_LOGIN"))
    env_server = os.environ.get("OMEGA_MT5_SERVER")
    env_password = os.environ.get("OMEGA_MT5_PASSWORD")

    resolved_login = login if login is not None else env_login
    if resolved_login is None and profile_data:
        resolved_login = _maybe_int(profile_data.get("login"))

    resolved_password = password if password is not None else env_password
    if resolved_password is None and profile_data:
        resolved_password = profile_data.get("password")

    resolved_server = server or env_server
    if resolved_server is None and profile_data:
        resolved_server = profile_data.get("server")

    description = (profile_data or {}).get("description") if profile_data else ""
    default_symbol = (profile_data or {}).get("default_symbol", "EURUSD")
    terminal_path = (profile_data or {}).get("terminal_path")

    return Mt5AccountConfig(
        name=profile_name.upper() if profile_name else "UNSPECIFIED",
        server=resolved_server,
        login=resolved_login,
        password=resolved_password,
        description=description or "",
        default_symbol=default_symbol or "EURUSD",
        terminal_path=terminal_path,
    )


def available_profile_names() -> list[str]:
    return sorted(load_account_profiles().keys())


def _maybe_int(value) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
