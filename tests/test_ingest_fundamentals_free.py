"""Demo fundamentals ingestion and PIT read-path tests."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import text

from azureus.data.db import sync_session
from azureus.data.sources.auditing import AuditingDataSource
from azureus.data.sources.yfinance_source import (
    YFinanceDataSource,
    _normalize_yfinance_fundamentals,
)
from azureus.pipelines import ingest_fundamentals_free as flow_module


def _seed_ticker(ticker: str = "0700.HK") -> None:
    with sync_session() as session:
        session.execute(
            text(
                "INSERT INTO tickers (ticker, name, exchange) "
                "VALUES (:ticker, :name, 'HKEX') "
                "ON CONFLICT (ticker) DO NOTHING"
            ),
            {"ticker": ticker, "name": f"Test {ticker}"},
        )


def _fundamentals_df(value: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "provider": "yfinance",
                "ticker": "0700.HK",
                "metric": "net_income",
                "period_end": dt.date(2024, 3, 31),
                "reported_date": dt.date(2024, 6, 29),
                "value": value,
                "unit": "currency",
                "is_restated": False,
            },
            {
                "provider": "yfinance",
                "ticker": "0700.HK",
                "metric": "book_value",
                "period_end": dt.date(2024, 3, 31),
                "reported_date": dt.date(2024, 6, 29),
                "value": 500.0,
                "unit": "currency",
                "is_restated": False,
            },
        ]
    )


def _insert_fundamental(
    *,
    ticker: str = "0700.HK",
    metric: str,
    period_end: dt.date,
    reported_date: dt.date,
    value: float,
) -> None:
    with sync_session() as session:
        session.execute(
            text(
                "INSERT INTO fundamentals_pit "
                "(provider, ticker, metric, period_end, reported_date, value, unit) "
                "VALUES ('yfinance', :ticker, :metric, :period_end, :reported_date, "
                ":value, 'currency')"
            ),
            {
                "ticker": ticker,
                "metric": metric,
                "period_end": period_end,
                "reported_date": reported_date,
                "value": value,
            },
        )


def test_normalize_yfinance_fundamentals_applies_conservative_reported_lag() -> None:
    income = pd.DataFrame(
        {
            pd.Timestamp("2024-03-31"): [100.0, 500.0],
            pd.Timestamp("2026-03-31"): [200.0, 900.0],
        },
        index=["Net Income", "Total Revenue"],
    )
    balance = pd.DataFrame(
        {pd.Timestamp("2024-03-31"): [1200.0]},
        index=["Stockholders Equity"],
    )

    df = _normalize_yfinance_fundamentals(
        "0700.HK",
        {"income": income, "balance": balance, "cashflow": pd.DataFrame()},
        today=dt.date(2024, 7, 1),
    )

    assert set(df["metric"]) == {"net_income", "total_revenue", "book_value"}
    assert set(df["period_end"]) == {dt.date(2024, 3, 31)}
    assert set(df["reported_date"]) == {dt.date(2024, 6, 29)}
    assert dt.date(2026, 3, 31) not in set(df["period_end"])


def test_flow_writes_fundamentals_and_lineage_on_success(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ticker()
    monkeypatch.setattr(
        flow_module,
        "fetch_fundamentals_from_yfinance",
        lambda ticker: _fundamentals_df(),
    )

    result = flow_module.ingest_fundamentals_free("0700.HK")

    assert result["status"] == "success"
    assert result["rows_inserted"] == 2
    assert result["ticker"] == "0700.HK"

    with sync_session() as session:
        fundamental_count = session.execute(
            text("SELECT COUNT(*) FROM fundamentals_pit WHERE ticker = '0700.HK'")
        ).scalar_one()
        run = (
            session.execute(
                text(
                    "SELECT pipeline_name, provider, table_name, status, rows_inserted, "
                    "errors, config FROM ingestion_runs ORDER BY id DESC LIMIT 1"
                )
            )
            .mappings()
            .one()
        )

    assert fundamental_count == 2
    assert run["pipeline_name"] == "ingest_fundamentals_free"
    assert run["provider"] == "yfinance"
    assert run["table_name"] == "fundamentals_pit"
    assert run["status"] == "success"
    assert run["rows_inserted"] == 2
    assert run["errors"] is None
    assert run["config"]["ticker"] == "0700.HK"
    assert run["config"]["reported_lag_days"] == 90
    assert "reproducibility" in run["config"]


def test_flow_is_idempotent_on_reingest(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ticker()
    monkeypatch.setattr(
        flow_module,
        "fetch_fundamentals_from_yfinance",
        lambda ticker: _fundamentals_df(value=100.0),
    )
    flow_module.ingest_fundamentals_free("0700.HK")

    monkeypatch.setattr(
        flow_module,
        "fetch_fundamentals_from_yfinance",
        lambda ticker: _fundamentals_df(value=111.0),
    )
    flow_module.ingest_fundamentals_free("0700.HK")

    with sync_session() as session:
        fundamental_count = session.execute(
            text("SELECT COUNT(*) FROM fundamentals_pit WHERE ticker = '0700.HK'")
        ).scalar_one()
        net_income = session.execute(
            text(
                "SELECT value FROM fundamentals_pit "
                "WHERE ticker = '0700.HK' AND metric = 'net_income'"
            )
        ).scalar_one()
        run_count = session.execute(text("SELECT COUNT(*) FROM ingestion_runs")).scalar_one()

    assert fundamental_count == 2
    assert net_income == Decimal("111.000000")
    assert run_count == 2


def test_flow_records_failed_run_when_fetch_raises(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ticker()

    def _boom(ticker: str) -> pd.DataFrame:
        raise RuntimeError(f"yfinance is down for {ticker}")

    monkeypatch.setattr(flow_module, "fetch_fundamentals_from_yfinance", _boom)

    with pytest.raises(RuntimeError, match="fundamentals ingestion failed"):
        flow_module.ingest_fundamentals_free("0700.HK")

    with sync_session() as session:
        run = (
            session.execute(
                text(
                    "SELECT status, rows_inserted, errors "
                    "FROM ingestion_runs ORDER BY id DESC LIMIT 1"
                )
            )
            .mappings()
            .one()
        )

    assert run["status"] == "failed"
    assert run["rows_inserted"] == 0
    assert run["errors"]["exception_type"] == "RuntimeError"
    assert "yfinance is down for 0700.HK" in run["errors"]["message"]


def test_yfinance_data_source_fundamentals_are_pit_correct(
    migrated_database: str,
) -> None:
    _seed_ticker()
    _insert_fundamental(
        metric="net_income",
        period_end=dt.date(2024, 3, 31),
        reported_date=dt.date(2024, 6, 29),
        value=100.0,
    )
    _insert_fundamental(
        metric="net_income",
        period_end=dt.date(2024, 6, 30),
        reported_date=dt.date(2024, 9, 28),
        value=200.0,
    )
    _insert_fundamental(
        metric="book_value",
        period_end=dt.date(2024, 3, 31),
        reported_date=dt.date(2024, 6, 29),
        value=500.0,
    )

    audited = AuditingDataSource(inner=YFinanceDataSource())
    df = audited.get_fundamentals(
        tickers=["0700.HK"],
        as_of_date=dt.date(2024, 7, 15),
        metrics=["net_income", "book_value"],
    )

    assert audited.lookahead_violations == 0
    assert set(df["metric"]) == {"net_income", "book_value"}
    assert (df["reported_date"] <= dt.date(2024, 7, 15)).all()
    assert df.loc[df["metric"] == "net_income", "period_end"].item() == dt.date(2024, 3, 31)
    assert df.loc[df["metric"] == "net_income", "value"].item() == Decimal("100.000000")

    history = YFinanceDataSource().get_fundamentals_history(
        tickers=["0700.HK"],
        start=dt.date(2024, 6, 1),
        end=dt.date(2024, 7, 15),
        metrics=["net_income", "book_value"],
    )

    assert set(history["metric"]) == {"net_income", "book_value"}
    assert set(YFinanceDataSource().list_available_metrics()) == {"book_value", "net_income"}
