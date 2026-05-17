"""Seed-script tests.

Two layers:

1. **Fixture-CSV mechanism tests** — use small CSVs under `tests/fixtures/`
   to verify the script reads, parses, upserts, and is idempotent. Fast,
   deterministic, decoupled from the real curated data.
2. **Production-CSV smoke tests** — load the real `data/universe/*.csv`
   files against the ephemeral DB and assert row counts + spot-check
   well-known tickers (`0700.HK`, `0005.HK`, `3690.HK`).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import text

from azureus.data.db import sync_session
from scripts import seed_tickers, seed_universe

_FIXTURES = Path(__file__).parent / "fixtures"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_TICKERS_CSV = _REPO_ROOT / "data" / "universe" / "tickers.csv"
_REAL_HSI_CSV = _REPO_ROOT / "data" / "universe" / "hsi_members.csv"


# ---------- mechanism tests against tests/fixtures/*.csv -----------------


def test_seed_tickers_inserts_all_rows(migrated_database: str) -> None:
    n = seed_tickers.main(_FIXTURES / "test_tickers.csv")
    assert n == 3

    with sync_session() as session:
        rows = session.execute(
            text("SELECT ticker, sector, listed_date FROM tickers ORDER BY ticker")
        ).all()

    tickers = {row.ticker for row in rows}
    assert tickers == {"TEST.HK", "LATE.HK", "MIN.HK"}

    late_row = next(row for row in rows if row.ticker == "LATE.HK")
    assert late_row.listed_date == dt.date(2022, 5, 10)
    assert late_row.sector == "Information Technology"

    min_row = next(row for row in rows if row.ticker == "MIN.HK")
    assert min_row.sector is None, "empty CSV cells must parse to NULL"


def test_seed_tickers_is_idempotent(migrated_database: str) -> None:
    seed_tickers.main(_FIXTURES / "test_tickers.csv")
    seed_tickers.main(_FIXTURES / "test_tickers.csv")  # rerun

    with sync_session() as session:
        count = session.execute(text("SELECT COUNT(*) FROM tickers")).scalar_one()
    assert count == 3, "ON CONFLICT DO UPDATE must not duplicate rows"


def test_seed_universe_inserts_all_rows(migrated_database: str) -> None:
    # Tickers must be seeded first — FK constraint.
    seed_tickers.main(_FIXTURES / "test_tickers.csv")
    n = seed_universe.main(_FIXTURES / "test_hsi_members.csv")
    assert n == 3

    with sync_session() as session:
        rows = session.execute(
            text(
                "SELECT ticker, start_date, end_date, weight_at_entry "
                "FROM universe_membership WHERE index_id = 'TEST_IDX' "
                "ORDER BY ticker"
            )
        ).all()

    by_ticker = {row.ticker: row for row in rows}
    assert by_ticker["TEST.HK"].start_date == dt.date(2014, 1, 1)
    assert by_ticker["TEST.HK"].end_date is None
    assert by_ticker["TEST.HK"].weight_at_entry is not None

    assert by_ticker["MIN.HK"].end_date == dt.date(2020, 3, 31)
    assert by_ticker["LATE.HK"].weight_at_entry is None


def test_seed_universe_is_idempotent(migrated_database: str) -> None:
    seed_tickers.main(_FIXTURES / "test_tickers.csv")
    seed_universe.main(_FIXTURES / "test_hsi_members.csv")
    seed_universe.main(_FIXTURES / "test_hsi_members.csv")  # rerun

    with sync_session() as session:
        count = session.execute(text("SELECT COUNT(*) FROM universe_membership")).scalar_one()
    assert count == 3


def test_seed_universe_fails_without_tickers(migrated_database: str) -> None:
    """FK violation when tickers aren't seeded first — error must surface, not be swallowed."""
    with pytest.raises(Exception, match="foreign key"):
        seed_universe.main(_FIXTURES / "test_hsi_members.csv")


# ---------- smoke tests against the real curated CSVs --------------------


def test_real_tickers_csv_loads_and_has_min_size(migrated_database: str) -> None:
    n = seed_tickers.main(_REAL_TICKERS_CSV)
    assert n >= 60, f"real tickers CSV shrunk below v1 floor (got {n})"

    with sync_session() as session:
        # Spot-check several anchors that should always exist.
        for ticker in ("0700.HK", "0005.HK", "3690.HK", "9988.HK"):
            row = session.execute(
                text("SELECT ticker, name, sector FROM tickers WHERE ticker = :t"),
                {"t": ticker},
            ).one()
            assert row.name, f"{ticker} missing name"
            assert row.sector, f"{ticker} missing sector"


def test_real_universe_csv_loads_and_resolves_fks(migrated_database: str) -> None:
    """Loading the real universe CSV must succeed after loading the real tickers CSV."""
    seed_tickers.main(_REAL_TICKERS_CSV)
    n = seed_universe.main(_REAL_HSI_CSV)
    assert n >= 60

    with sync_session() as session:
        # Late addition: Meituan should have its HK listing date, not 2014-01-01.
        row = session.execute(
            text(
                "SELECT start_date FROM universe_membership "
                "WHERE index_id = 'HSI' AND ticker = '3690.HK'"
            )
        ).one()
        assert row.start_date == dt.date(2018, 9, 20)

        # Anchor: Tencent should be in HSI from 2014 (or earlier).
        row = session.execute(
            text(
                "SELECT start_date FROM universe_membership "
                "WHERE index_id = 'HSI' AND ticker = '0700.HK'"
            )
        ).one()
        assert row.start_date == dt.date(2014, 1, 1)
