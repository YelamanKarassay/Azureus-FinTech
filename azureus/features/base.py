"""Feature interface for Strategy 1 and later strategies.

Features are provider-agnostic computations over a `DataSource`. They return
one scalar per ticker for a single `as_of_date`; callers combine them into
cross-sectional scores and exclude missing values rather than imputing.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol

import pandas as pd

from azureus.data.sources.base import DataSource


class Feature(Protocol):
    """Provider-agnostic feature computation contract."""

    name: str
    description: str
    family: str
    requires_metrics: tuple[str, ...]
    requires_lookback_days: int

    def compute(
        self,
        data: DataSource,
        tickers: list[str],
        as_of_date: dt.date,
    ) -> pd.Series:
        """Return a `ticker -> feature_value` series for `as_of_date`."""
