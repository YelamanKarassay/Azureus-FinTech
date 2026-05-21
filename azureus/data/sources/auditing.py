"""`AuditingDataSource` — runtime enforcement of Hard Rule 1 (PIT correctness).

The single most important correctness check in the project. Wraps any
concrete `DataSource` and asserts the most-cited PIT invariant: rows
returned by `get_fundamentals(as_of_date=D)` must never have
`reported_date > D`.

ARCHITECTURE §3.1 names this wrapper as the mechanism that makes
"no lookahead is structurally possible" testable rather than aspirational.
This module + `tests/test_pit_regression.py` are the project's signature
methodology test.

What is **not** audited (by design, in Phase 1):

- `get_prices` — daily bars have no disclosure lag (close prices report
  at session close, same day as `date`). No PIT concept applies.
- `get_macro` — has `reported_date` in the row payload but the Protocol
  signature does not currently take `as_of_date`. Until the Protocol
  evolves, the auditor cannot tell what `as_of_date` *should* be at the
  call site.
- `get_fundamentals_history` — by design returns `reported_date` so the
  caller (e.g. feature engineering) can do its own PIT filtering. This
  method is not used by the backtester directly.
- `get_universe_history` — returns membership intervals, not point-in-
  time values.

These omissions are deliberate and reviewable; expand the audit when the
Protocol or use-cases change.
"""

from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from azureus.data.sources.base import DataSource

logger = logging.getLogger(__name__)

_REPORTED_DATE_COL = "reported_date"


class LookaheadError(AssertionError):
    """A `DataSource` returned data dated after the requested `as_of_date`.

    Subclasses `AssertionError` because this is a methodological-correctness
    failure — a backtest that hits this has computed an invalid result.
    """


class AuditingDataSource:
    """Drop-in `DataSource` wrapper that asserts PIT invariants on every call.

    Construction:
        audit = AuditingDataSource(inner=YFinanceDataSource())

    Use in tests, in CI smoke checks, and behind a `STRICT_MODE` flag in
    the backtester (Phase 2+). When wrapped, queries cost an additional
    DataFrame mask scan per call — not a hot-path consideration at our
    backtest cadence (a few rebalances per simulation year).
    """

    def __init__(self, inner: DataSource) -> None:
        self._inner = inner
        # Diagnostic counters — useful in tests asserting the audit actually fired.
        self.fundamentals_calls: int = 0
        self.lookahead_violations: int = 0

    @property
    def provider_name(self) -> str:
        return f"audit({self._inner.provider_name})"

    # ---- audited path -----------------------------------------------------

    def get_fundamentals(
        self,
        tickers: list[str],
        as_of_date: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        df = self._inner.get_fundamentals(tickers, as_of_date, metrics)
        self.fundamentals_calls += 1
        self._assert_no_lookahead(df, as_of_date, method="get_fundamentals")
        return df

    # ---- pass-through paths (no PIT semantics or no as_of_date) -----------

    def get_universe(self, index_id: str, as_of_date: dt.date) -> list[str]:
        return self._inner.get_universe(index_id, as_of_date)

    def get_universe_history(
        self,
        index_id: str,
        start: dt.date,
        end: dt.date,
    ) -> pd.DataFrame:
        return self._inner.get_universe_history(index_id, start, end)

    def get_prices(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        fields: tuple[str, ...] = ("close",),
    ) -> pd.DataFrame:
        return self._inner.get_prices(tickers, start, end, fields)

    def get_fundamentals_history(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        return self._inner.get_fundamentals_history(tickers, start, end, metrics)

    def get_macro(
        self,
        series_ids: list[str],
        start: dt.date,
        end: dt.date,
    ) -> pd.DataFrame:
        return self._inner.get_macro(series_ids, start, end)

    def list_available_tickers(self, index_id: str | None = None) -> list[str]:
        return self._inner.list_available_tickers(index_id)

    def list_available_metrics(self) -> list[str]:
        return self._inner.list_available_metrics()

    # ---- internals --------------------------------------------------------

    def _assert_no_lookahead(
        self,
        df: pd.DataFrame,
        as_of_date: dt.date,
        *,
        method: str,
    ) -> None:
        """Raise `LookaheadError` if any row reports after `as_of_date`."""
        if df.empty or _REPORTED_DATE_COL not in df.columns:
            return

        reported = pd.to_datetime(df[_REPORTED_DATE_COL]).dt.date
        violation_mask = reported > as_of_date
        if not violation_mask.any():
            return

        self.lookahead_violations += int(violation_mask.sum())
        violations = df.loc[violation_mask]
        sample = violations.head(3).to_dict(orient="records")
        raise LookaheadError(
            f"Hard Rule 1 violation in {self.provider_name}.{method}: "
            f"{len(violations)} row(s) with reported_date > as_of_date={as_of_date}. "
            f"Sample: {sample}"
        )
