"""Pydantic value objects for internal data shapes.

These travel across module boundaries (data layer → feature layer → strategy
layer → API). They are distinct from:
- ORM models (`azureus.data.models`): DB-shaped, session-bound, mutable.
- API request/response schemas (`azureus.api.schemas`, Phase 3): wire-shaped
  for HTTP, may differ in field naming / nesting from the internal models.

Models are frozen so they can be safely passed between threads / async tasks.
`from_attributes=True` allows construction directly from ORM instances.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)


class TickerMetadata(_Frozen):
    """Reference metadata for a single ticker."""

    ticker: str
    name: str
    exchange: str
    sector: str | None = None
    industry: str | None = None
    currency: str = "HKD"
    is_active: bool = True
    listed_date: dt.date | None = None
    delisted_date: dt.date | None = None


class PriceBar(_Frozen):
    """A single OHLCV bar.

    `close` is the unadjusted reference price. `adjusted_close` carries
    corporate-action adjustments and is the canonical column for return
    calculations.
    """

    provider: str
    ticker: str
    date: dt.date
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal
    adjusted_close: Decimal | None = None
    volume: int | None = None


class Fundamental(_Frozen):
    """Point-in-time fundamental data point.

    `reported_date` is the date the value became publicly known. Strategy
    code never sees rows where `reported_date > as_of_date` (Hard Rule 1).
    """

    provider: str
    ticker: str
    metric: str
    period_end: dt.date
    reported_date: dt.date
    value: Decimal | None = None
    unit: str | None = None
    is_restated: bool = False


class MacroValue(_Frozen):
    """Point-in-time macro data point. Same PIT semantics as `Fundamental`."""

    provider: str
    series_id: str
    date: dt.date
    value: Decimal | None = None
    reported_date: dt.date


class UniverseMember(_Frozen):
    """A single (index, ticker) membership interval.

    `end_date is None` ⇒ still a member as of the latest universe snapshot.
    """

    index_id: str
    ticker: str
    start_date: dt.date
    end_date: dt.date | None = None
    weight_at_entry: Decimal | None = None
