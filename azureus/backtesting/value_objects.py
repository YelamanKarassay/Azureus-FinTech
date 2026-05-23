"""Backtester value objects — frozen Pydantic models for trade lifecycle.

Three lifecycle points:

1. `Trade` — what the strategy + portfolio diff produced. An *intent*.
2. `ExecutedTrade` — what came back from the cost model. All cost
   components are broken out so analytics can attribute drag.
3. `Position` / `PortfolioSnapshot` — daily holdings for the equity curve.

Signed-shares convention throughout: positive shares = long; negative =
short. v1 is long-only so negative `Trade.shares` always means closing
or trimming an existing position, never opening a short. `Portfolio`
enforces this at apply-time.

All monetary values are HKD floats. NUMERIC precision discipline
(CLAUDE.md "Common Mistakes" #7) applies at the DB boundary — the
in-memory representation can be float.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    """Immutable, hashable Pydantic base — value objects flow across modules."""

    model_config = ConfigDict(frozen=True)


class Trade(_Frozen):
    """An intended trade, produced by the engine from a weight diff.

    `shares` is signed; `reference_price` is the price used to size it
    (typically yesterday's close, per the one-day signal lag rule).
    """

    ticker: str
    shares: float
    reference_price: float


class ExecutedTrade(_Frozen):
    """A filled trade with every HK cost component broken out.

    Round-trip total = commission + stamp_duty + sfc_levy + hkex_fee +
    ccass_fee + slippage. `total_cost` is the sum; cost analytics
    re-aggregate it by category for the cost-drag chart.

    `net_cash_change` is the signed cash impact: negative for buys
    (cash leaves), positive for sells (cash arrives minus fees).
    """

    ticker: str
    executed_at: dt.date
    shares: float
    fill_price: float
    gross_notional: float

    commission: float
    stamp_duty: float
    sfc_levy: float
    hkex_fee: float
    ccass_fee: float
    slippage: float
    total_cost: float

    net_cash_change: float


class Position(_Frozen):
    """Snapshot of a single holding at a single point in time."""

    ticker: str
    shares: float
    last_price: float
    market_value: float


class PortfolioSnapshot(_Frozen):
    """Daily portfolio state — one row per trading day on the equity curve."""

    as_of_date: dt.date
    cash: float
    total_value: float
    holdings: dict[str, Position]
