"""PIT correctness regression test — the project's signature methodology test.

Per CLAUDE.md, Hard Rule 1: "PIT (Point-In-Time) Correctness Is Non-Negotiable".
Per ARCHITECTURE §3.1, this test makes the claim "no lookahead is structurally
possible at the data layer" verifiable rather than aspirational.

Test layers:

1. **Audit mechanics** — using a tiny `InMemoryFundamentalsSource` that
   honestly filters by `reported_date <= as_of_date`, verify the
   `AuditingDataSource` wrapper never spuriously fires.
2. **Lookahead detection** — using a `LeakyFundamentalsSource` that
   intentionally returns post-`as_of_date` rows, verify the wrapper
   raises `LookaheadError`.
3. **Synthetic backtest walk** — iterate over a year of monthly
   rebalances against a multi-ticker / multi-metric fundamentals
   universe; assert the audit fires zero times against the honest source
   across the full walk.
4. **Pass-throughs** — verify `get_prices` and other non-PIT methods are
   not gated by the audit (no PIT concept applies).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pytest

from azureus.data.sources.auditing import AuditingDataSource, LookaheadError

# ---- Synthetic PIT corpus -----------------------------------------------
#
# Two tickers ("T1", "T2"), one metric ("earnings"), four quarterly fiscal
# periods in 2024 each reported ~60 days after period_end (typical HK
# disclosure lag). Plus one Q4-2023 row reported in 2024 to give early
# 2024 backtests something to see.
#
# Backtests at 2024-03-01 should see only the 2023-Q4 row.
# Backtests at 2024-12-01 should see Q1, Q2, Q3 2024 (but not Q4 2024
# because Q4 reports ~end of Feb 2025).

_PIT_ROWS: list[dict[str, Any]] = []
for ticker in ("T1", "T2"):
    _PIT_ROWS.extend(
        [
            {
                "ticker": ticker,
                "metric": "earnings",
                "period_end": dt.date(2023, 12, 31),
                "reported_date": dt.date(2024, 2, 28),
                "value": 100.0,
            },
            {
                "ticker": ticker,
                "metric": "earnings",
                "period_end": dt.date(2024, 3, 31),
                "reported_date": dt.date(2024, 5, 30),
                "value": 110.0,
            },
            {
                "ticker": ticker,
                "metric": "earnings",
                "period_end": dt.date(2024, 6, 30),
                "reported_date": dt.date(2024, 8, 29),
                "value": 120.0,
            },
            {
                "ticker": ticker,
                "metric": "earnings",
                "period_end": dt.date(2024, 9, 30),
                "reported_date": dt.date(2024, 11, 29),
                "value": 130.0,
            },
            {
                "ticker": ticker,
                "metric": "earnings",
                "period_end": dt.date(2024, 12, 31),
                "reported_date": dt.date(2025, 2, 28),
                "value": 140.0,
            },
        ]
    )

PIT_CORPUS = pd.DataFrame(_PIT_ROWS)


# ---- Two in-memory DataSource fakes -------------------------------------


@dataclass
class InMemoryFundamentalsSource:
    """Honest PIT-correct in-memory fundamentals source.

    Filters `reported_date <= as_of_date` exactly as a production
    DataSource must (Hard Rule 1).
    """

    corpus: pd.DataFrame = field(default_factory=lambda: PIT_CORPUS.copy())
    provider_name: str = "fake-honest"

    def get_fundamentals(
        self,
        tickers: list[str],
        as_of_date: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        df = self.corpus
        mask = (
            df["ticker"].isin(tickers)
            & df["metric"].isin(metrics)
            & (df["reported_date"] <= as_of_date)
        )
        return df.loc[mask].reset_index(drop=True)

    # Methods unused by these tests can remain stubs — they're only here so
    # `AuditingDataSource` can structurally treat this object as a DataSource.
    def get_universe(self, index_id: str, as_of_date: dt.date) -> list[str]:
        return ["T1", "T2"]

    def get_universe_history(self, index_id: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_prices(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        fields: tuple[str, ...] = ("close",),
    ) -> pd.DataFrame:
        # Build a tiny no-reported_date frame so we can verify get_prices
        # is NOT gated by the audit.
        return pd.DataFrame({"date": [start], "ticker": [tickers[0]], "close": [100.0]})

    def get_fundamentals_history(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        return self.corpus.copy()

    def get_macro(self, series_ids: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        return pd.DataFrame()

    def list_available_tickers(self, index_id: str | None = None) -> list[str]:
        return ["T1", "T2"]

    def list_available_metrics(self) -> list[str]:
        return ["earnings"]


@dataclass
class LeakyFundamentalsSource(InMemoryFundamentalsSource):
    """Intentionally buggy: ignores `reported_date` filter — leaks future data."""

    provider_name: str = "fake-leaky"

    def get_fundamentals(
        self,
        tickers: list[str],
        as_of_date: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        df = self.corpus
        mask = df["ticker"].isin(tickers) & df["metric"].isin(metrics)
        # BUG: no `reported_date <= as_of_date` filter.
        return df.loc[mask].reset_index(drop=True)


# ---- Tests ---------------------------------------------------------------


def test_audit_passes_when_inner_filters_correctly() -> None:
    audit = AuditingDataSource(inner=InMemoryFundamentalsSource())

    # 2024-03-01: only 2023-Q4 has been reported (2024-02-28).
    df = audit.get_fundamentals(
        tickers=["T1", "T2"],
        as_of_date=dt.date(2024, 3, 1),
        metrics=["earnings"],
    )

    assert audit.lookahead_violations == 0
    assert audit.fundamentals_calls == 1
    assert len(df) == 2  # one row per ticker, period_end=2023-12-31
    assert (df["period_end"] == dt.date(2023, 12, 31)).all()


def test_audit_raises_when_inner_leaks_future_data() -> None:
    audit = AuditingDataSource(inner=LeakyFundamentalsSource())

    # Q4-2024 statement isn't out until 2025-02-28. A query on 2024-12-01
    # MUST NOT see it. The leaky source returns it; the audit must fire.
    with pytest.raises(LookaheadError, match="reported_date > as_of_date"):
        audit.get_fundamentals(
            tickers=["T1"],
            as_of_date=dt.date(2024, 12, 1),
            metrics=["earnings"],
        )

    assert audit.lookahead_violations >= 1


def test_audit_walks_synthetic_backtest_without_firing() -> None:
    """Monthly rebalances across 2024 against the honest source — zero violations."""
    audit = AuditingDataSource(inner=InMemoryFundamentalsSource())

    rebalance_dates = [dt.date(2024, month, 1) for month in range(1, 13)] + [dt.date(2025, 1, 1)]

    rows_per_date: dict[dt.date, int] = {}
    for sim_date in rebalance_dates:
        df = audit.get_fundamentals(
            tickers=["T1", "T2"],
            as_of_date=sim_date,
            metrics=["earnings"],
        )
        rows_per_date[sim_date] = len(df)

    assert audit.lookahead_violations == 0
    assert audit.fundamentals_calls == len(rebalance_dates)

    # Spot-check the timeline against the disclosure-lag corpus:
    # 2024-01-01: nothing reported yet (2023-Q4 lands 2024-02-28)
    assert rows_per_date[dt.date(2024, 1, 1)] == 0
    # 2024-03-01: 2023-Q4 visible for both tickers
    assert rows_per_date[dt.date(2024, 3, 1)] == 2
    # 2024-12-01: Q4-2023 + Q1-2024 + Q2-2024 + Q3-2024 = 4 periods × 2 tickers
    assert rows_per_date[dt.date(2024, 12, 1)] == 8
    # 2025-01-01: still no Q4-2024 (reports 2025-02-28)
    assert rows_per_date[dt.date(2025, 1, 1)] == 8


def test_audit_does_not_gate_get_prices() -> None:
    """`get_prices` has no `reported_date` concept; the audit must pass through."""
    audit = AuditingDataSource(inner=InMemoryFundamentalsSource())

    df = audit.get_prices(
        tickers=["T1"],
        start=dt.date(2024, 1, 1),
        end=dt.date(2024, 12, 31),
    )

    assert not df.empty
    assert audit.lookahead_violations == 0
    assert audit.fundamentals_calls == 0, "get_prices must not be counted as a fundamentals call"


def test_audit_handles_empty_response() -> None:
    """Empty DataFrame from inner is valid — no rows, no violations."""
    audit = AuditingDataSource(inner=InMemoryFundamentalsSource())

    df = audit.get_fundamentals(
        tickers=["NONEXISTENT.HK"],
        as_of_date=dt.date(2024, 6, 30),
        metrics=["earnings"],
    )

    assert df.empty
    assert audit.lookahead_violations == 0


def test_audit_provider_name_wraps_inner() -> None:
    """Operational ergonomics — lineage should show the wrap explicitly."""
    audit = AuditingDataSource(inner=InMemoryFundamentalsSource())
    assert audit.provider_name == "audit(fake-honest)"


def test_audit_passes_through_universe_calls() -> None:
    """`get_universe` returns a list of strings — no PIT data to validate."""
    audit = AuditingDataSource(inner=InMemoryFundamentalsSource())
    tickers = audit.get_universe("HSI", dt.date(2024, 6, 30))
    assert tickers == ["T1", "T2"]
    assert audit.fundamentals_calls == 0
