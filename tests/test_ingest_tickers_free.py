"""Ticker-metadata refresh flow tests.

yfinance is patched out; we drive the refresh against a small seeded
universe and assert (a) names get updated, (b) sector/industry are
NOT touched (CSV remains authoritative), (c) failures land in the
lineage row's `errors` payload.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from azureus.data.db import sync_session
from azureus.pipelines import ingest_tickers_free as flow_module

_SEED_ROWS = [
    ("0700.HK", "Old Tencent Name", "Communication Services", "Interactive Media"),
    ("STALE.HK", "Stale Inc", "Industrials", "Conglomerate"),
    ("BROKEN.HK", "Broken Co", "Financials", "Banks"),
]


def _seed_tickers_with_metadata() -> None:
    with sync_session() as session:
        for ticker, name, sector, industry in _SEED_ROWS:
            session.execute(
                text(
                    "INSERT INTO tickers (ticker, name, exchange, sector, industry) "
                    "VALUES (:t, :n, 'HKEX', :s, :i)"
                ),
                {"t": ticker, "n": name, "s": sector, "i": industry},
            )


def test_refreshes_names_without_touching_sector_or_industry(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_tickers_with_metadata()

    new_names = {
        "0700.HK": "Tencent Holdings Ltd",
        "STALE.HK": "Stale Inc",  # same — should be a no-op update
        "BROKEN.HK": "Broken Co Renamed",
    }
    monkeypatch.setattr(flow_module, "_resolve_name", lambda ticker: new_names[ticker])

    result = flow_module.ingest_tickers_free(tickers=list(new_names.keys()))

    assert result["status"] == "success"
    assert result["tickers_total"] == 3
    assert result["rows_updated"] == 2  # STALE.HK was unchanged
    assert result["rows_failed"] == 0

    with sync_session() as session:
        rows = (
            session.execute(
                text("SELECT ticker, name, sector, industry FROM tickers ORDER BY ticker")
            )
            .mappings()
            .all()
        )

    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["0700.HK"]["name"] == "Tencent Holdings Ltd"
    assert by_ticker["0700.HK"]["sector"] == "Communication Services", "sector untouched"
    assert by_ticker["BROKEN.HK"]["name"] == "Broken Co Renamed"
    assert by_ticker["BROKEN.HK"]["industry"] == "Banks", "industry untouched"


def test_records_yfinance_failures_in_lineage(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_tickers_with_metadata()

    def resolver(ticker: str) -> str | None:
        if ticker == "BROKEN.HK":
            raise RuntimeError("yfinance returned 429")
        if ticker == "STALE.HK":
            return None  # yfinance returned info dict but no name fields
        return "Tencent Holdings Ltd"

    monkeypatch.setattr(flow_module, "_resolve_name", resolver)

    result = flow_module.ingest_tickers_free(tickers=["0700.HK", "STALE.HK", "BROKEN.HK"])

    assert result["status"] == "partial"
    assert result["rows_updated"] == 1
    assert result["rows_failed"] == 2

    with sync_session() as session:
        run = (
            session.execute(
                text(
                    "SELECT status, rows_updated, rows_failed, errors "
                    "FROM ingestion_runs "
                    "WHERE pipeline_name = 'ingest_tickers_free' "
                    "ORDER BY id DESC LIMIT 1"
                )
            )
            .mappings()
            .one()
        )

    assert run["status"] == "partial"
    assert run["rows_updated"] == 1
    assert run["rows_failed"] == 2

    failures = {item["ticker"]: item["reason"] for item in run["errors"]["failures"]}
    assert "BROKEN.HK" in failures
    assert "yfinance returned 429" in failures["BROKEN.HK"]
    assert failures["STALE.HK"] == "no name from yfinance"


def test_defaults_to_all_active_tickers(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with sync_session() as session:
        session.execute(
            text(
                "INSERT INTO tickers (ticker, name, exchange, is_active) VALUES "
                "('A.HK', 'A Co', 'HKEX', true), "
                "('B.HK', 'B Co', 'HKEX', true), "
                "('C.HK', 'C Co', 'HKEX', false)"
            )
        )

    monkeypatch.setattr(flow_module, "_resolve_name", lambda ticker: f"Refreshed {ticker}")

    result = flow_module.ingest_tickers_free()  # no `tickers` arg → all active

    assert result["tickers_total"] == 2
    assert result["rows_updated"] == 2

    with sync_session() as session:
        c_name = session.execute(
            text("SELECT name FROM tickers WHERE ticker = 'C.HK'")
        ).scalar_one()
    assert c_name == "C Co", "inactive ticker must not be refreshed"
