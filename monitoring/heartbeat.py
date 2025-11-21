"""Heartbeat monitoring for dead man's switch."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

STATE_PATH = Path("config/bot_state.json")


class HeartbeatMonitor:
    """Sends periodic heartbeats to detect system failures."""

    def __init__(
        self,
        healthcheck_url: Optional[str] = None,
        interval_seconds: int = 300,
    ):
        """Initialize heartbeat monitor.
        
        Args:
            healthcheck_url: URL to ping (e.g., healthchecks.io UUID)
            interval_seconds: How often to send heartbeat
        """
        self.healthcheck_url = healthcheck_url
        self.interval_seconds = interval_seconds
        self.last_beat: Optional[datetime] = None

    def beat(self, metadata: Optional[dict] = None) -> bool:
        """Send a heartbeat ping.
        
        Args:
            metadata: Optional data to include in ping
            
        Returns:
            True if successful, False otherwise
        """
        self.last_beat = datetime.utcnow()

        # Update state file
        self._update_state(metadata)

        # Ping external service if configured
        if self.healthcheck_url:
            return self._ping_external(metadata)

        return True

    def _update_state(self, metadata: Optional[dict] = None) -> None:
       """Update bot state file with heartbeat timestamp."""
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        state = {}
        if STATE_PATH.exists():
            try:
                state = json.loads(STATE_PATH.read_text())
            except json.JSONDecodeError:
                logger.warning("Could not parse bot state file")

        state["last_heartbeat"] = self.last_beat.isoformat()
        if metadata:
            state["last_heartbeat_metadata"] = metadata

        STATE_PATH.write_text(json.dumps(state, indent=2))

    def _ping_external(self, metadata: Optional[dict] = None) -> bool:
        """Ping external healthcheck service."""
        if not self.healthcheck_url:
            return False

        try:
            # Healthchecks.io supports attaching metadata via POST body
            if metadata:
                response = requests.post(
                    self.healthcheck_url,
                    json=metadata,
                    timeout=10,
                )
            else:
                response = requests.get(self.healthcheck_url, timeout=10)

            if response.status_code == 200:
                logger.debug("Heartbeat ping successful")
                return True
            else:
                logger.warning(
                    f"Heartbeat ping returned {response.status_code}: {response.text}"
                )
                return False

        except requests.RequestException as e:
            logger.error(f"Heartbeat ping failed: {e}")
            return False


def create_heartbeat_monitor(config_path: Path = Path("config/healthcheck.yaml")) -> HeartbeatMonitor:
    """Create heartbeat monitor from config file.
    
    Args:
        config_path: Path to healthcheck configuration
        
    Returns:
        Configured HeartbeatMonitor instance
    """
    if not config_path.exists():
        logger.info(f"Healthcheck config not found at {config_path}, using defaults")
        return HeartbeatMonitor()

    try:
        import yaml
        config = yaml.safe_load(config_path.read_text())
        
        healthcheck_url = config.get("healthcheck_url")
        interval = config.get("interval_seconds", 300)

        return HeartbeatMonitor(
            healthcheck_url=healthcheck_url,
            interval_seconds=interval,
        )
    except Exception as e:
        logger.error(f"Failed to load healthcheck config: {e}")
        return HeartbeatMonitor()
