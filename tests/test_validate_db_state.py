"""validate_db_state flow tests.

Each test seeds a focused DB state, runs the flow, and asserts the
expected status + result shape + lineage row.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from azureus.data.db import sync_session
from azureus.pipelines import validate_db_state as flow_module


def _seed_ticker(ticker: str = "0700.HK") -> None:
    with sync_session() as session:
        session.execute(
            text(
                "INSERT INTO tickers (ticker, name, exchange) VALUES (:t, :n, 'HKEX') "
                "ON CONFLICT (ticker) DO NOTHING"
            ),
            {"t": ticker, "n": f"Test {ticker}"},
        )


def _seed_universe(ticker: str = "0700.HK", index_id: str = "HSI") -> None:
    with sync_session() as session:
        session.execute(
            text(
                "INSERT INTO universe_membership (index_id, ticker, start_date) "
                "VALUES (:i, :t, :s) "
                "ON CONFLICT (index_id, ticker, start_date) DO NOTHING"
            ),
            {"i": index_id, "t": ticker, "s": dt.date(2014, 1, 1)},
        )


def _seed_price(
    ticker: str = "0700.HK",
    bar_date: dt.date | None = None,
    close: float = 400.0,
) -> None:
    bar_date = bar_date or (dt.date.today() - dt.timedelta(days=1))
    with sync_session() as session:
        session.execute(
            text(
                "INSERT INTO prices (provider, ticker, date, close) "
                "VALUES ('yfinance', :t, :d, :c) "
                "ON CONFLICT (provider, ticker, date) DO NOTHING"
            ),
            {"t": ticker, "d": bar_date, "c": close},
        )


def test_clean_state_returns_success(migrated_database: str) -> None:
    _seed_ticker()
    _seed_universe()
    _seed_price()

    summary = flow_module.validate_db_state()

    assert summary["status"] == "success"
    assert summary["errors"] == 0
    assert summary["warnings"] == 0
    assert summary["results"] == []

    with sync_session() as session:
        run = (
            session.execute(
                text(
                    "SELECT status, rows_failed, config "
                    "FROM ingestion_runs WHERE pipeline_name = 'validate_db_state' "
                    "ORDER BY id DESC LIMIT 1"
                )
            )
            .mappings()
            .one()
        )
    assert run["status"] == "success"
    assert run["rows_failed"] == 0
    assert "checks_run" in run["config"]


def test_future_price_date_triggers_error(migrated_database: str) -> None:
    _seed_ticker()
    _seed_universe()
    _seed_price()
    future = dt.date.today() + dt.timedelta(days=30)
    _seed_price(bar_date=future)

    with pytest.raises(RuntimeError, match="validation failed"):
        flow_module.validate_db_state()

    with sync_session() as session:
        run = (
            session.execute(
                text(
                    "SELECT status, errors FROM ingestion_runs "
                    "WHERE pipeline_name = 'validate_db_state' "
                    "ORDER BY id DESC LIMIT 1"
                )
            )
            .mappings()
            .one()
        )

    assert run["status"] == "failed"
    names = [r["name"] for r in run["errors"]["results"]]
    assert "no_future_price_dates" in names


def test_missing_universe_member_triggers_warning(migrated_database: str) -> None:
    """A universe member with zero price rows triggers a warning, not an error."""
    _seed_ticker("0700.HK")
    _seed_ticker("0011.HK")
    _seed_universe("0700.HK")
    _seed_universe("0011.HK")  # universe member, intentionally no prices
    _seed_price("0700.HK")

    summary = flow_module.validate_db_state()

    assert summary["status"] == "partial"
    assert summary["errors"] == 0
    assert summary["warnings"] >= 1

    coverage_result = next(
        (r for r in summary["results"] if r["name"] == "universe_coverage"), None
    )
    assert coverage_result is not None
    assert coverage_result["severity"] == "warning"
    assert "0011.HK" in coverage_result["details"]["missing_tickers"]


def test_stale_ingest_triggers_warning(migrated_database: str) -> None:
    _seed_ticker()
    _seed_universe()
    _seed_price(bar_date=dt.date.today() - dt.timedelta(days=90))

    summary = flow_module.validate_db_state()

    assert summary["status"] == "partial"
    stale_result = next((r for r in summary["results"] if r["name"] == "recent_ingest"), None)
    assert stale_result is not None
    assert stale_result["severity"] == "warning"
    assert stale_result["details"]["days_old"] >= 60


def test_empty_db_reports_stale_warning(migrated_database: str) -> None:
    """No tickers, no universe, no prices — single warning, no errors."""
    summary = flow_module.validate_db_state()

    assert summary["status"] == "partial"
    assert summary["errors"] == 0
    names = {r["name"] for r in summary["results"]}
    assert "recent_ingest" in names


def test_lineage_row_records_check_inventory(migrated_database: str) -> None:
    """The config column should record which checks were run, for auditing."""
    _seed_ticker()
    _seed_universe()
    _seed_price()

    flow_module.validate_db_state()

    with sync_session() as session:
        run = (
            session.execute(
                text(
                    "SELECT config FROM ingestion_runs "
                    "WHERE pipeline_name = 'validate_db_state' "
                    "ORDER BY id DESC LIMIT 1"
                )
            )
            .mappings()
            .one()
        )

    checks = run["config"]["checks_run"]
    assert "_check_no_future_price_dates" in checks
    assert "_check_universe_coverage" in checks
    assert "_check_recent_ingest" in checks
