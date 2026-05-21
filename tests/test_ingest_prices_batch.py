"""Batch ingest tests — fan-out, partial failure, ticker selection.

Concurrency is forced to 1 in tests so per-ticker ordering is deterministic.
The underlying `fetch_prices_from_yfinance` is patched out — no network.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pandas as pd
import pytest
from sqlalchemy import text

from azureus.data.db import sync_session
from azureus.pipelines import ingest_prices_batch as batch_module
from azureus.pipelines import ingest_prices_free as flow_module


def _seed_tickers(tickers: list[str]) -> None:
    with sync_session() as session:
        for ticker in tickers:
            session.execute(
                text(
                    "INSERT INTO tickers (ticker, name, exchange) "
                    "VALUES (:t, :n, 'HKEX') "
                    "ON CONFLICT (ticker) DO NOTHING"
                ),
                {"t": ticker, "n": f"Test {ticker}"},
            )


def _make_synthetic_for_ticker(ticker: str, n_bars: int = 30) -> pd.DataFrame:
    """Generate a clean synthetic prices DataFrame for an arbitrary ticker."""
    dates = pd.bdate_range(end=pd.Timestamp(dt.date.today() - dt.timedelta(days=1)), periods=n_bars)
    return pd.DataFrame(
        {
            "provider": "yfinance",
            "ticker": ticker,
            "date": dates,
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
            "adjusted_close": 105.0,
            "volume": pd.array([1_000_000] * n_bars, dtype="Int64"),
        }
    )


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, behavior: Callable[[str], pd.DataFrame]) -> None:
    """Replace the lower-level yfinance fetch used by the shared helper."""
    monkeypatch.setattr(
        flow_module,
        "fetch_prices_from_yfinance",
        lambda ticker, start, end: behavior(ticker),
    )


def test_batch_runs_all_tickers_and_writes_per_ticker_lineage(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tickers = ["0700.HK", "0005.HK", "3690.HK"]
    _seed_tickers(tickers)
    _patch_fetch(monkeypatch, _make_synthetic_for_ticker)

    result = batch_module.ingest_prices_batch_free(tickers=tickers, lookback_days=30, concurrency=1)

    assert result["status"] == "success"
    assert result["tickers_total"] == 3
    assert result["tickers_success"] == 3
    assert result["tickers_failed"] == 0
    assert result["failed_tickers"] == []
    assert result["total_rows_inserted"] == 90  # 3 tickers × 30 bars

    with sync_session() as session:
        # one prices row per ticker × 30 days
        price_count = session.execute(
            text("SELECT COUNT(*) FROM prices WHERE ticker = ANY(:t)"),
            {"t": tickers},
        ).scalar_one()
        # one ingestion_runs row per ticker
        run_count = session.execute(
            text("SELECT COUNT(*) FROM ingestion_runs WHERE pipeline_name = 'ingest_prices_free'")
        ).scalar_one()
        # all rows marked success
        success_count = session.execute(
            text(
                "SELECT COUNT(*) FROM ingestion_runs "
                "WHERE pipeline_name = 'ingest_prices_free' AND status = 'success'"
            )
        ).scalar_one()

    assert price_count == 90
    assert run_count == 3
    assert success_count == 3


def test_batch_returns_partial_when_one_ticker_fails(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tickers = ["0700.HK", "BROKEN.HK", "0005.HK"]
    _seed_tickers(tickers)

    def fetch_behavior(ticker: str) -> pd.DataFrame:
        if ticker == "BROKEN.HK":
            raise RuntimeError("yfinance is down for this ticker")
        return _make_synthetic_for_ticker(ticker)

    _patch_fetch(monkeypatch, fetch_behavior)

    result = batch_module.ingest_prices_batch_free(tickers=tickers, lookback_days=30, concurrency=1)

    assert result["status"] == "partial"
    assert result["tickers_success"] == 2
    assert result["tickers_failed"] == 1
    assert result["failed_tickers"] == ["BROKEN.HK"]
    assert result["total_rows_inserted"] == 60

    with sync_session() as session:
        failed_run = (
            session.execute(
                text(
                    "SELECT errors->>'exception_type' AS exc_type, errors->>'message' AS msg "
                    "FROM ingestion_runs "
                    "WHERE pipeline_name = 'ingest_prices_free' AND status = 'failed' "
                    "ORDER BY id DESC LIMIT 1"
                )
            )
            .mappings()
            .one()
        )

    assert failed_run["exc_type"] == "RuntimeError"
    assert "yfinance is down" in failed_run["msg"]


def test_batch_raises_when_all_tickers_fail(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tickers = ["A.HK", "B.HK"]
    _seed_tickers(tickers)

    def _always_fail(ticker: str) -> pd.DataFrame:
        raise RuntimeError("catastrophic outage")

    _patch_fetch(monkeypatch, _always_fail)

    with pytest.raises(RuntimeError, match="batch ingestion failed for all 2 tickers"):
        batch_module.ingest_prices_batch_free(tickers=tickers, lookback_days=30, concurrency=1)

    with sync_session() as session:
        failed_count = session.execute(
            text("SELECT COUNT(*) FROM ingestion_runs WHERE status = 'failed'")
        ).scalar_one()
    assert failed_count == 2, "every per-ticker failure must still write its lineage row"


def test_batch_with_no_tickers_returns_noop(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Patch is irrelevant since the flow won't fetch anything, but we set it
    # anyway so the test fails loudly if the flow ever does call out.
    _patch_fetch(monkeypatch, _make_synthetic_for_ticker)
    result = batch_module.ingest_prices_batch_free(tickers=[], concurrency=1)

    assert result["status"] == "noop"
    assert result["tickers_total"] == 0
    assert result["total_rows_inserted"] == 0


def test_batch_loads_all_active_tickers_when_tickers_is_none(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed two active + one inactive ticker.
    with sync_session() as session:
        session.execute(
            text(
                "INSERT INTO tickers (ticker, name, exchange, is_active) VALUES "
                "('ACTIVE1.HK', 'Active 1', 'HKEX', true), "
                "('ACTIVE2.HK', 'Active 2', 'HKEX', true), "
                "('INACTIVE.HK', 'Inactive', 'HKEX', false)"
            )
        )

    _patch_fetch(monkeypatch, _make_synthetic_for_ticker)

    result = batch_module.ingest_prices_batch_free(tickers=None, concurrency=1)

    assert result["tickers_total"] == 2, "inactive tickers must be excluded"
    assert set(result["failed_tickers"]) == set()
