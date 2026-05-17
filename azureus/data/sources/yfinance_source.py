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
                "provider": "object",
                "ticker": "object",
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
    # Nullable Int64 for volume; float64 for OHLC are pandas defaults.
    df["volume"] = df["volume"].astype("Int64")
    # Drop rows missing close — see docstring.
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    # pandas-stubs types reset_index() as Any; an explicit annotation pins it.
    result: pd.DataFrame = df
    return result


class YFinanceDataSource:
    """Read implementation of `DataSource` over our `yfinance`-provider tables."""

    provider_name: str = PROVIDER_NAME

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
                        "provider": PROVIDER_NAME,
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
        raise NotImplementedError(
            "Fundamentals ingestion lands in Phase 1 Days 9-11 — see PHASE_1_CHECKLIST.md"
        )

    def get_fundamentals_history(
        self,
        tickers: list[str],
        start: dt.date,
        end: dt.date,
        metrics: list[str],
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "Fundamentals ingestion lands in Phase 1 Days 9-11 — see PHASE_1_CHECKLIST.md"
        )

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
        raise NotImplementedError(
            "Fundamentals ingestion lands in Phase 1 Days 9-11 — see PHASE_1_CHECKLIST.md"
        )
