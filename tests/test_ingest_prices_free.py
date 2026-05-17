"""End-to-end ingestion tests against a migrated ephemeral DB.

`yfinance` is patched out so tests don't depend on the network or upstream
availability. A separate live test (skipped by default) hits the real API.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import text

from azureus.data.db import sync_session
from azureus.pipelines import ingest_prices_free as flow_module


def _seed_ticker(ticker: str, name: str = "Tencent Holdings", exchange: str = "HKEX") -> None:
    with sync_session() as session:
        session.execute(
            text("INSERT INTO tickers (ticker, name, exchange) VALUES (:t, :n, :e)"),
            {"t": ticker, "n": name, "e": exchange},
        )


def test_flow_writes_prices_and_lineage_on_success(
    migrated_database: str,
    synthetic_prices_df: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_ticker("0700.HK")
    monkeypatch.setattr(
        flow_module,
        "fetch_prices_from_yfinance",
        lambda ticker, start, end: synthetic_prices_df,
    )

    result = flow_module.ingest_prices_free(ticker="0700.HK", lookback_days=30)

    assert result["status"] == "success"
    assert result["rows_inserted"] == 30
    assert result["ticker"] == "0700.HK"

    with sync_session() as session:
        price_count = session.execute(
            text("SELECT COUNT(*) FROM prices WHERE ticker = '0700.HK'")
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

    assert price_count == 30
    assert run["pipeline_name"] == "ingest_prices_free"
    assert run["provider"] == "yfinance"
    assert run["table_name"] == "prices"
    assert run["status"] == "success"
    assert run["rows_inserted"] == 30
    assert run["errors"] is None
    assert run["config"]["ticker"] == "0700.HK"
    assert "reproducibility" in run["config"]


def test_flow_is_idempotent_on_reingest(
    migrated_database: str,
    synthetic_prices_df: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running the flow with the same data must not duplicate rows."""
    _seed_ticker("0700.HK")
    monkeypatch.setattr(
        flow_module,
        "fetch_prices_from_yfinance",
        lambda ticker, start, end: synthetic_prices_df,
    )

    flow_module.ingest_prices_free(ticker="0700.HK", lookback_days=30)
    flow_module.ingest_prices_free(ticker="0700.HK", lookback_days=30)

    with sync_session() as session:
        price_count = session.execute(
            text("SELECT COUNT(*) FROM prices WHERE ticker = '0700.HK'")
        ).scalar_one()
        run_count = session.execute(text("SELECT COUNT(*) FROM ingestion_runs")).scalar_one()

    assert price_count == 30, "ON CONFLICT DO UPDATE must keep one row per key"
    assert run_count == 2, "every flow invocation must record its own lineage row"


def test_flow_records_failed_run_when_fetch_raises(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure inside fetch must still produce a `failed` ingestion_runs row."""
    _seed_ticker("0700.HK")

    def _boom(*args: object, **kwargs: object) -> pd.DataFrame:
        raise RuntimeError("yfinance is down")

    monkeypatch.setattr(flow_module, "fetch_prices_from_yfinance", _boom)

    with pytest.raises(RuntimeError, match="ingestion failed"):
        flow_module.ingest_prices_free(ticker="0700.HK", lookback_days=30)

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
    assert "yfinance is down" in run["errors"]["message"]


def test_data_source_get_prices_reads_back_what_flow_wrote(
    migrated_database: str,
    synthetic_prices_df: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The DataSource read path returns what the ingestion write path put in."""
    from azureus.data.sources.yfinance_source import YFinanceDataSource

    _seed_ticker("0700.HK")
    monkeypatch.setattr(
        flow_module,
        "fetch_prices_from_yfinance",
        lambda ticker, start, end: synthetic_prices_df,
    )
    flow_module.ingest_prices_free(ticker="0700.HK", lookback_days=30)

    ds = YFinanceDataSource()
    df = ds.get_prices(
        tickers=["0700.HK"],
        start=dt.date.today() - dt.timedelta(days=60),
        end=dt.date.today(),
        fields=("close", "volume"),
    )

    assert len(df) == 30
    assert set(df.columns) == {"date", "provider", "ticker", "close", "volume"}
    assert df["provider"].unique().tolist() == ["yfinance"]
    assert df["ticker"].unique().tolist() == ["0700.HK"]
