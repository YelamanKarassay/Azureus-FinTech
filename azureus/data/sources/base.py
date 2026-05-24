"""`DataSource` Protocol — the abstraction strategies depend on (§3.4).

Hard Rule 2: strategy code touches `DataSource` only — never a concrete
provider class. Hard Rule 1: every time-aware method takes `as_of_date`
and never returns rows with `reported_date > as_of_date`.

Return-shape convention (locked):
- Time-series methods (`get_prices`, `get_fundamentals_history`, `get_macro`,
  `get_universe_history`) return long-format `pandas.DataFrame`. Tidy long is
  closer to the storage layer; feature code pivots to wide as needed.
- Reference methods (`get_universe`, `list_available_tickers`,
  `list_available_metrics`) return plain `list[str]`.
- Point-in-time fundamentals (`get_fundamentals`) returns a long-format
  `DataFrame` (one row per ticker × metric), with each row carrying the
  latest `value` known on `as_of_date` for that key.

Concrete implementations (`YFinanceDataSource`, `BloombergDataSource`) read
from our Postgres tables — they do not call the upstream vendor at query
time. Ingestion pipelines populate the tables; the DataSource consumes them.
This decoupling is what makes backtests reproducible (§3.10).
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol

import pandas as pd


class DataSource(Protocol):
    """The interface every data provider must implement.

    Implementations expose `provider_name` so jobs can record which provider
    produced their inputs (§3.10 reproducibility). Declared as a read-only
    property so wrappers (`AuditingDataSource`) that derive it from an inner
    source satisfy the Protocol; concrete sources with a literal class
    attribute also satisfy it (LSP: more-permissive implementations are OK).
    """

    @property
    def provider_name(self) -> str: ...

    def get_universe(self, index_id: str, as_of_date: dt.date) -> list[str]:
        """Tickers that are members of `index_id` on `as_of_date`.

        Args:
            index_id: e.g. "HSI", "HSCEI".
            as_of_date: simulation date in a backtest.
        """
        ...

    def get_universe_history(
        self,
        index_id: str,
        start: dt.date,
        end: dt.date,
    ) -> pd.DataFrame:
        """Full interval-table view of universe membership over a date range.

        Columns: `ticker`, `start_date`, `end_date` (nullable), `weight_at_entry`.
        """
        ...

    def get_prices(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        fields: tuple[str, ...] = ("close",),
    ) -> pd.DataFrame:
        """Daily OHLCV bars for the given tickers in `[start, end]`.

        Long format. Columns: `date`, `provider`, `ticker`, plus the
        requested `fields` (subset of `open`, `high`, `low`, `close`,
        `adjusted_close`, `volume`).
        """
        ...

    def get_fundamentals(
        self,
        tickers: list[str],
        as_of_date: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        """Point-in-time fundamentals snapshot.

        For each (ticker, metric), returns the most recent value with
        `reported_date <= as_of_date`. Tickers missing any requested metric
        are excluded for that metric row (v1 has no imputation —
        "Common Mistakes" #4).
        """
        ...

    def get_fundamentals_history(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        """Full history of (ticker × metric) values reported in `[start, end]`.

        Columns: `ticker`, `metric`, `period_end`, `reported_date`, `value`,
        `unit`, `is_restated`, `provider`. Use this to construct features
        that need a time-series of fundamentals, not just a snapshot.
        """
        ...

    def get_macro(
        self,
        series_ids: list[str],
        start: dt.date,
        end: dt.date,
    ) -> pd.DataFrame:
        """Macro series values in `[start, end]`.

        Columns: `date`, `series_id`, `value`, `reported_date`, `provider`.
        """
        ...

    def list_available_tickers(self, index_id: str | None = None) -> list[str]:
        """All tickers the provider has data for; optionally filtered by index."""
        ...

    def list_available_metrics(self) -> list[str]:
        """Fundamental metric names this provider supports."""
        ...
