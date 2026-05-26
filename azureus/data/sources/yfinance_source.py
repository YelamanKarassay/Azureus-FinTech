"""YFinance data provider — fetches from yfinance, reads from our Postgres tables.

Two responsibilities:
1. `fetch_prices_from_yfinance` — calls the yfinance API, returns a normalized
   DataFrame ready for Pandera validation and upsert. Used by ingestion flows.
2. `YFinanceDataSource` — implements the `DataSource` Protocol by reading
   from our `prices` / `tickers` / etc. tables, never from yfinance directly.
   This decoupling is what makes backtests reproducible (§3.10): the strategy
   sees a frozen view of the DB, not a live API.

HK ticker format: yfinance uses `0700.HK` (zero-padded 4-digit + `.HK`). This
is our internal canonical form — see CLAUDE.md "Common Mistakes" #5 (always
specify provider). Bloomberg-format translation lives in Phase 5.

Methods not yet exercised by Phase 1 ingestion raise `NotImplementedError`;
they fill in as later pipelines come online.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping
from typing import Any

import pandas as pd
import yfinance as yf
from sqlalchemy import bindparam, text

from azureus.data.db import sync_session

logger = logging.getLogger(__name__)

PROVIDER_NAME = "yfinance"

_YF_COLUMN_MAP = {
    "Date": "date",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adjusted_close",
    "Volume": "volume",
}

_PRICE_COLUMNS = [
    "provider",
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
]

_FUNDAMENTAL_COLUMNS = [
    "provider",
    "ticker",
    "metric",
    "period_end",
    "reported_date",
    "value",
    "unit",
    "is_restated",
]

_FUNDAMENTAL_REPORTED_LAG_DAYS = 90

_STATEMENT_METRICS: dict[str, tuple[str, tuple[str, ...]]] = {
    "net_income": (
        "income",
        (
            "Net Income",
            "Net Income Common Stockholders",
            "Net Income From Continuing Operation Net Minority Interest",
        ),
    ),
    "total_revenue": ("income", ("Total Revenue", "Operating Revenue")),
    "gross_profit": ("income", ("Gross Profit",)),
    "basic_eps": ("income", ("Basic EPS",)),
    "diluted_eps": ("income", ("Diluted EPS",)),
    "book_value": (
        "balance",
        (
            "Stockholders Equity",
            "Common Stock Equity",
            "Total Equity Gross Minority Interest",
        ),
    ),
    "total_assets": ("balance", ("Total Assets",)),
    "total_liabilities": (
        "balance",
        ("Total Liabilities Net Minority Interest", "Total Liab"),
    ),
    "total_debt": ("balance", ("Total Debt", "Net Debt")),
    "ordinary_shares": ("balance", ("Ordinary Shares Number", "Share Issued")),
    "free_cash_flow": ("cashflow", ("Free Cash Flow",)),
    "operating_cash_flow": (
        "cashflow",
        ("Operating Cash Flow", "Total Cash From Operating Activities"),
    ),
    "capital_expenditure": ("cashflow", ("Capital Expenditure", "Capital Expenditures")),
}


def fetch_prices_from_yfinance(
    ticker: str,
    start: dt.date,
    end: dt.date,
) -> pd.DataFrame:
    """Fetch daily OHLCV for one ticker over `[start, end]`.

    Returns a long-format DataFrame matching `PRICES_SCHEMA`. Rows with a
    null `close` (holidays, pre-listing, suspensions) are dropped — we never
    persist a bar without a close. `auto_adjust=False` keeps raw OHLC; adjusted
    close lands in its own column for return calculations.

    Caller validates with `PRICES_SCHEMA` before persisting.
    """
    handle = yf.Ticker(ticker)
    # yfinance treats `end` as exclusive — bump by one day to make the
    # API match our inclusive convention.
    hist = handle.history(
        start=start.isoformat(),
        end=(end + dt.timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=False,
    )

    if hist.empty:
        logger.warning("yfinance returned no rows for %s [%s, %s]", ticker, start, end)
        empty: dict[str, list[object]] = {col: [] for col in _PRICE_COLUMNS}
        return pd.DataFrame(empty).astype(
            {
                # `string` (pandas StringDtype) — not `object`. Pandera 0.20+
                # strictly checks dtype names on empty DataFrames; object on
                # an empty frame trips the validator even though row-bearing
                # frames slide by.
                "provider": "string",
                "ticker": "string",
                "date": "datetime64[ns]",
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "adjusted_close": "float64",
                "volume": "Int64",
            }
        )

    # yfinance returns DatetimeIndex (timezone-aware for some markets).
    # Strip timezone to satisfy our naive datetime64[ns] schema.
    if hist.index.tz is not None:
        hist.index = hist.index.tz_localize(None)

    df = hist.reset_index().rename(columns=_YF_COLUMN_MAP)
    df["provider"] = PROVIDER_NAME
    df["ticker"] = ticker
    df = df[_PRICE_COLUMNS]
    # Explicit dtypes — see comment in the empty branch.
    df["provider"] = df["provider"].astype("string")
    df["ticker"] = df["ticker"].astype("string")
    df["volume"] = df["volume"].astype("Int64")
    # Drop rows missing close — see docstring.
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    # pandas-stubs types reset_index() as Any; an explicit annotation pins it.
    result: pd.DataFrame = df
    return result


def fetch_fundamentals_from_yfinance(
    ticker: str,
    *,
    today: dt.date | None = None,
) -> pd.DataFrame:
    """Fetch yfinance statements and normalize annual+quarterly PIT rows.

    yfinance does not provide true announcement timestamps consistently for
    HK equities. For the public demo path we use a conservative PIT proxy:
    `reported_date = period_end + 90 days`. Rows whose proxy reported date
    is after `today` are skipped so the DB never contains future
    `reported_date` values.
    """
    as_of_today = today or dt.date.today()
    handle = yf.Ticker(ticker)
    statements = {
        "income": _merge_statement_frames(handle.quarterly_income_stmt, handle.income_stmt),
        "balance": _merge_statement_frames(
            handle.quarterly_balance_sheet,
            handle.balance_sheet,
        ),
        "cashflow": _merge_statement_frames(handle.quarterly_cashflow, handle.cashflow),
    }
    return _normalize_yfinance_fundamentals(ticker, statements, as_of_today)


def _normalize_yfinance_fundamentals(
    ticker: str,
    statements: Mapping[str, pd.DataFrame],
    today: dt.date,
) -> pd.DataFrame:
    """Normalize raw yfinance statement frames into long PIT rows."""
    rows: list[dict[str, Any]] = []
    for metric, (statement_name, aliases) in _STATEMENT_METRICS.items():
        statement = statements.get(statement_name, pd.DataFrame())
        if statement.empty:
            continue
        source_row = _first_available_row(statement, aliases)
        if source_row is None:
            continue
        for period, value in source_row.items():
            if pd.isna(value):
                continue
            period_end = _period_to_date(period)
            reported_date = period_end + dt.timedelta(days=_FUNDAMENTAL_REPORTED_LAG_DAYS)
            if reported_date > today:
                continue
            rows.append(
                {
                    "provider": PROVIDER_NAME,
                    "ticker": ticker,
                    "metric": metric,
                    "period_end": period_end,
                    "reported_date": reported_date,
                    "value": float(value),
                    "unit": _metric_unit(metric),
                    "is_restated": False,
                }
            )

    if not rows:
        return pd.DataFrame({col: [] for col in _FUNDAMENTAL_COLUMNS})

    df = pd.DataFrame(rows, columns=_FUNDAMENTAL_COLUMNS)
    return df.sort_values(["ticker", "metric", "period_end"]).reset_index(drop=True)


def _first_available_row(statement: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series | None:
    """Return the first matching yfinance statement row for the alias list."""
    for alias in aliases:
        if alias in statement.index:
            row: pd.Series = statement.loc[statement.index == alias].iloc[0]
            return row
    return None


def _merge_statement_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    """Merge yfinance annual and quarterly statement frames by statement row."""
    usable = [frame for frame in frames if not frame.empty]
    if not usable:
        return pd.DataFrame()
    merged = pd.concat(usable, axis=1, join="outer")
    merged = merged.loc[:, ~merged.columns.duplicated()]
    return merged


def _period_to_date(period: object) -> dt.date:
    """Convert a yfinance statement column label into a date."""
    if isinstance(period, pd.Timestamp):
        return period.date()
    if isinstance(period, dt.datetime):
        return period.date()
    if isinstance(period, dt.date):
        return period
    return pd.Timestamp(str(period)).date()


def _metric_unit(metric: str) -> str:
    """Compact unit label that fits the DB's `unit` column."""
    return "shares" if metric == "ordinary_shares" else "currency"


class YFinanceDataSource:
    """Read implementation of `DataSource` over our `yfinance`-provider tables."""

    provider_name: str = PROVIDER_NAME
    price_provider_name: str = PROVIDER_NAME
    fundamentals_provider_name: str = PROVIDER_NAME

    def get_universe(self, index_id: str, as_of_date: dt.date) -> list[str]:
        with sync_session() as session:
            rows = session.execute(
                text(
                    "SELECT ticker FROM universe_membership "
                    "WHERE index_id = :idx "
                    "AND start_date <= :d "
                    "AND (end_date IS NULL OR end_date >= :d) "
                    "ORDER BY ticker"
                ),
                {"idx": index_id, "d": as_of_date},
            ).all()
        return [row[0] for row in rows]

    def get_universe_history(
        self,
        index_id: str,
        start: dt.date,
        end: dt.date,
    ) -> pd.DataFrame:
        with sync_session() as session:
            rows = (
                session.execute(
                    text(
                        "SELECT ticker, start_date, end_date, weight_at_entry "
                        "FROM universe_membership "
                        "WHERE index_id = :idx "
                        "AND start_date <= :end "
                        "AND (end_date IS NULL OR end_date >= :start) "
                        "ORDER BY ticker, start_date"
                    ),
                    {"idx": index_id, "start": start, "end": end},
                )
                .mappings()
                .all()
            )
        return pd.DataFrame(rows)

    def get_prices(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        fields: tuple[str, ...] = ("close",),
    ) -> pd.DataFrame:
        allowed = {"open", "high", "low", "close", "adjusted_close", "volume"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown price fields: {sorted(unknown)}")

        select_cols = ", ".join(["date", "provider", "ticker", *fields])
        stmt = text(
            f"SELECT {select_cols} FROM prices "  # noqa: S608  -- fields are whitelisted above
            "WHERE provider = :provider "
            "AND ticker IN :tickers "
            "AND date BETWEEN :start AND :end "
            "ORDER BY date, ticker"
        ).bindparams(bindparam("tickers", expanding=True))

        with sync_session() as session:
            rows = (
                session.execute(
                    stmt,
                    {
                        "provider": self.price_provider_name,
                        "tickers": tickers,
                        "start": start,
                        "end": end,
                    },
                )
                .mappings()
                .all()
            )
        return pd.DataFrame(rows)

    def get_fundamentals(
        self,
        tickers: list[str],
        as_of_date: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        if not tickers or not metrics:
            return pd.DataFrame()

        stmt = text(
            """
            SELECT DISTINCT ON (ticker, metric)
                   provider, ticker, metric, period_end, reported_date,
                   value, unit, is_restated
            FROM fundamentals_pit
            WHERE provider = :provider
              AND ticker IN :tickers
              AND metric IN :metrics
              AND reported_date <= :as_of_date
            ORDER BY ticker, metric, reported_date DESC, period_end DESC
            """
        ).bindparams(
            bindparam("tickers", expanding=True),
            bindparam("metrics", expanding=True),
        )

        with sync_session() as session:
            rows = (
                session.execute(
                    stmt,
                    {
                        "provider": self.fundamentals_provider_name,
                        "tickers": tickers,
                        "metrics": metrics,
                        "as_of_date": as_of_date,
                    },
                )
                .mappings()
                .all()
            )
        return pd.DataFrame(rows)

    def get_fundamentals_history(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        if not tickers or not metrics:
            return pd.DataFrame()

        stmt = text(
            """
            SELECT provider, ticker, metric, period_end, reported_date,
                   value, unit, is_restated
            FROM fundamentals_pit
            WHERE provider = :provider
              AND ticker IN :tickers
              AND metric IN :metrics
              AND reported_date BETWEEN :start AND :end
            ORDER BY ticker, metric, reported_date, period_end
            """
        ).bindparams(
            bindparam("tickers", expanding=True),
            bindparam("metrics", expanding=True),
        )

        with sync_session() as session:
            rows = (
                session.execute(
                    stmt,
                    {
                        "provider": self.fundamentals_provider_name,
                        "tickers": tickers,
                        "metrics": metrics,
                        "start": start,
                        "end": end,
                    },
                )
                .mappings()
                .all()
            )
        return pd.DataFrame(rows)

    def get_macro(
        self,
        series_ids: list[str],
        start: dt.date,
        end: dt.date,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "Macro ingestion is scheduled for late Phase 1 — see PHASE_1_CHECKLIST.md"
        )

    def list_available_tickers(self, index_id: str | None = None) -> list[str]:
        if index_id is None:
            with sync_session() as session:
                rows = session.execute(
                    text("SELECT ticker FROM tickers WHERE is_active ORDER BY ticker")
                ).all()
        else:
            with sync_session() as session:
                rows = session.execute(
                    text(
                        "SELECT DISTINCT ticker FROM universe_membership "
                        "WHERE index_id = :idx ORDER BY ticker"
                    ),
                    {"idx": index_id},
                ).all()
        return [row[0] for row in rows]

    def list_available_metrics(self) -> list[str]:
        with sync_session() as session:
            rows = session.execute(
                text(
                    "SELECT DISTINCT metric FROM fundamentals_pit "
                    "WHERE provider = :provider ORDER BY metric"
                ),
                {"provider": self.fundamentals_provider_name},
            ).all()
        return [row[0] for row in rows]
