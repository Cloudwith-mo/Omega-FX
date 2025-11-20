"""Strategy implementations and registry bindings."""

from core.strategy_registry import register_strategy
from .omega import OmegaM15Strategy

register_strategy(
    tag="omega_m15",
    namespace="strategies.omega.m15",
    cls=OmegaM15Strategy,
    description="OmegaFX base 15-minute strategy",
)

__all__ = ["OmegaM15Strategy"]
