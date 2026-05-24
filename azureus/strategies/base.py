"""Strategy contract — Protocol + `StrategyContext`.

Phase 2 (Day 18) sketch: minimum surface the `BacktestEngine` needs to
drive a backtest. Two methods on the Protocol — `rebalance_dates` and
`target_weights` — plus the immutable `StrategyContext` value passed
into each `target_weights` call.

Day 21 layers the full Strategy ABC on top (Pydantic `params_model`,
optional `fit`, registry decorator). The engine's call surface stays
identical, so the Day 21 expansion is additive — no engine refactor.

The Protocol uses structural typing: any class with the two methods is
a Strategy as far as the engine is concerned. Day 21 will introduce an
abstract base class that satisfies this Protocol so concrete strategies
inherit the params plumbing, but the engine continues to treat the
contract structurally.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class StrategyContext(BaseModel):
    """Frozen snapshot the engine hands a strategy on each rebalance call.

    `as_of_date` is the date the strategy's signals are based on — per the
    one-day signal-lag convention (ARCHITECTURE §4.6), this is the trading
    day *before* the rebalance day. Strategy code passes `as_of_date` into
    any `DataSource.get_fundamentals(as_of_date=...)` query so the audit
    wrapper enforces PIT correctness.

    `universe` and `current_weights` are point-in-time snapshots. Mutating
    them is meaningless (the model is frozen); the engine produces a fresh
    context on every rebalance.
    """

    model_config = ConfigDict(frozen=True)

    as_of_date: dt.date
    universe: list[str]
    portfolio_value: float
    current_weights: dict[str, float]


class Strategy(Protocol):
    """The interface the `BacktestEngine` consumes.

    Day 21 will expand this with `id` / `name` / `description` / `params_model`
    / `fit` (for ML strategies in Phase 4) per ARCHITECTURE §4.3. For Day 18
    the engine only needs the two methods below.
    """

    def rebalance_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """Calendar dates on which `target_weights` should be queried.

        May fall on non-trading days — the engine rolls each forward to
        the next trading session before dispatching.
        """
        ...

    def target_weights(self, ctx: StrategyContext) -> dict[str, float]:
        """Desired portfolio weights, as fractions of total value.

        Tickers omitted (or set to 0) are sold out. Weights need not sum to
        1.0 — residual is cash. Negative weights are not allowed in v1
        (long-only per Hard Rule 1 + Portfolio enforcement).
        """
        ...
