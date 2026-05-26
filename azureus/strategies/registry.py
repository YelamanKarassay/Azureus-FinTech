"""Strategy registry for API/UI discovery."""

from __future__ import annotations

from azureus.strategies.base import Strategy
from azureus.strategies.benchmark import EqualWeightedHSIBenchmark
from azureus.strategies.gbm_factors_v1 import GBMFactorsV1Strategy
from azureus.strategies.multi_factor_v1 import MultiFactorV1Strategy

_STRATEGIES: dict[str, type[Strategy]] = {}


def register(strategy_cls: type[Strategy]) -> type[Strategy]:
    """Register a concrete strategy class by its stable id."""
    if strategy_cls.id in _STRATEGIES:
        raise ValueError(f"strategy id already registered: {strategy_cls.id}")
    _STRATEGIES[strategy_cls.id] = strategy_cls
    return strategy_cls


def list_strategies() -> list[type[Strategy]]:
    """Registered strategy classes, sorted by id for deterministic API output."""
    return [_STRATEGIES[strategy_id] for strategy_id in sorted(_STRATEGIES)]


def get_strategy(strategy_id: str) -> type[Strategy]:
    """Return a registered strategy class by id."""
    try:
        return _STRATEGIES[strategy_id]
    except KeyError as exc:
        raise KeyError(f"unknown strategy id: {strategy_id}") from exc


register(EqualWeightedHSIBenchmark)
register(GBMFactorsV1Strategy)
register(MultiFactorV1Strategy)
