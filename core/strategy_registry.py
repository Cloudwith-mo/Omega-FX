from __future__ import annotations

import builtins
from dataclasses import dataclass


@dataclass(frozen=True)
class StrategySpec:
    """Descriptor for a trading strategy implementation."""

    tag: str
    namespace: str
    cls: type
    description: str = ""


class StrategyRegistry:
    """Simple registry mapping strategy tags to implementations."""

    def __init__(self) -> None:
        self._registry: dict[str, StrategySpec] = {}

    def register(
        self,
        tag: str,
        *,
        namespace: str,
        cls: type,
        description: str = "",
    ) -> StrategySpec:
        key = tag.lower()
        spec = StrategySpec(
            tag=key,
            namespace=namespace,
            cls=cls,
            description=description,
        )
        self._registry[key] = spec
        return spec

    def get(self, tag: str) -> StrategySpec:
        key = tag.lower()
        if key not in self._registry:
            raise KeyError(f"Strategy '{tag}' is not registered.")
        return self._registry[key]

    def list(self) -> builtins.list[StrategySpec]:
        return list(self._registry.values())


_registry = StrategyRegistry()


def register_strategy(
    tag: str, *, namespace: str, cls: type, description: str = ""
) -> StrategySpec:
    return _registry.register(
        tag, namespace=namespace, cls=cls, description=description
    )


def get_strategy_spec(tag: str) -> StrategySpec:
    return _registry.get(tag)


def get_strategy_class(tag: str) -> type:
    return get_strategy_spec(tag).cls


def list_strategies() -> list[StrategySpec]:
    return _registry.list()


__all__ = [
    "StrategyRegistry",
    "StrategySpec",
    "register_strategy",
    "get_strategy_spec",
    "get_strategy_class",
    "list_strategies",
]
