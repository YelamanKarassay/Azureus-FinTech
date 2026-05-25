"""Locked Strategy contract per ARCHITECTURE §4.3.

Concrete strategies inherit `Strategy`, define a Pydantic params model,
and implement two methods the backtester calls: `rebalance_dates` and
`target_weights`. The optional `fit` hook is intentionally present now
so Phase 4 ML strategies do not need to change the interface.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from azureus.data.sources.base import DataSource


class StrategyParams(BaseModel):
    """Base class for strategy parameter models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class StrategyContext(BaseModel):
    """Frozen snapshot the engine hands a strategy on each rebalance call.

    `as_of_date` is the date the strategy's signals are based on: per the
    one-day signal-lag convention, this is the trading day before execution.
    Strategies pass it into `DataSource` methods with PIT semantics.
    """

    model_config = ConfigDict(frozen=True)

    as_of_date: dt.date
    universe: list[str]
    portfolio_value: float
    current_weights: dict[str, float]


class Strategy(ABC):
    """Abstract base class for all backtestable strategies."""

    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    params_model: ClassVar[type[StrategyParams]] = StrategyParams

    def __init__(self, params: StrategyParams, data: DataSource) -> None:
        self.params = params
        self.data = data
        self._setup()

    def _setup(self) -> None:
        """Optional one-time setup hook for concrete strategies."""
        return None

    def fit(self, train_start: dt.date, train_end: dt.date) -> None:
        """Optional fitting hook for ML strategies. No-op for deterministic strategies."""
        _ = (train_start, train_end)
        return None

    @abstractmethod
    def rebalance_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """Calendar dates on which `target_weights` should be queried.

        Dates may fall on non-trading days; the engine rolls them forward
        before dispatching.
        """

    @abstractmethod
    def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
        """Desired portfolio weights, as fractions of total value.

        Tickers omitted or set to zero are sold out. Weights need not sum to
        1.0; residual is cash. Negative weights are not allowed in v1.
        """
