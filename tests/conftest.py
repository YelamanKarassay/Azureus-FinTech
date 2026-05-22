"""Shared pytest fixtures for the Azureus test suite.

Two DB fixtures:

- `ephemeral_database` — creates an empty Postgres database for the test;
  yields a sync URL pointing at it; drops it on teardown. Used by raw
  migration tests that don't want any app code touching globals.
- `migrated_database` — depends on the above; applies migrations, swaps
  the app's settings to point at it, and clears the engine `lru_cache`
  so the next `sync_session()` / `async_session()` call hits the test DB.
  Used by ingestion / DataSource integration tests.

Both skip the test cleanly if `DATABASE_URL_SYNC` is unset, so CI without
Postgres stays green.

Prefect runs inside `prefect_test_harness` (auto-use, session-scoped) so
`@flow` and `@task` don't try to talk to a live Prefect API.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import pandas as pd
import pytest
from alembic.config import Config
from prefect.testing.utilities import prefect_test_harness
from sqlalchemy import create_engine, text

from alembic import command
from azureus.config import get_settings
from azureus.data import db as db_module


@pytest.fixture(scope="session", autouse=True)
def prefect_test_env() -> Iterator[None]:
    """Run all Prefect flows in an ephemeral test harness (SQLite, no server)."""
    with prefect_test_harness():
        yield


def _split_server_and_db(url: str) -> tuple[str, str]:
    server, db = url.rsplit("/", 1)
    return server, db


@pytest.fixture
def ephemeral_database() -> Iterator[str]:
    """Provision a uniquely-named test database; drop it after the test."""
    settings = get_settings()
    if not settings.database_url_sync:
        pytest.skip("DATABASE_URL_SYNC not set — skipping DB-dependent tests")

    server_url, _ = _split_server_and_db(settings.database_url_sync)
    test_db = f"test_azureus_{uuid.uuid4().hex[:8]}"
    test_url = f"{server_url}/{test_db}"
    admin_url = f"{server_url}/postgres"

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{test_db}"'))

    # Pre-install timescaledb outside any transaction. Alembic's transactional
    # DDL can't reliably install the extension and call `create_hypertable`
    # in the same transaction.
    bootstrap = create_engine(test_url, isolation_level="AUTOCOMMIT")
    with bootstrap.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    bootstrap.dispose()

    try:
        yield test_url
    finally:
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": test_db},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db}"'))
        admin_engine.dispose()


def _clear_db_engine_caches() -> None:
    """Dispose any cached engines first, then drop the lru_cache slots.

    Disposing avoids the ResourceWarning chain that pytest escalates to a
    test failure when psycopg / asyncpg sockets are GC'd while still open.
    Async disposal needs an event loop, which `asyncio.run()` provides.
    """
    if db_module.get_sync_engine.cache_info().currsize > 0:
        db_module.get_sync_engine().dispose()
    if db_module.get_async_engine.cache_info().currsize > 0:
        engine = db_module.get_async_engine()
        try:
            asyncio.run(engine.dispose())
        except RuntimeError:
            # Already inside an event loop (e.g. async test teardown).
            # Fall back to the underlying sync pool — won't fully release
            # the asyncpg transport, but matches what we can do here.
            engine.sync_engine.dispose()
    db_module.get_async_engine.cache_clear()
    db_module.get_sync_engine.cache_clear()
    db_module.get_async_sessionmaker.cache_clear()
    db_module.get_sync_sessionmaker.cache_clear()


@pytest.fixture
def migrated_database(
    ephemeral_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    """Ephemeral DB with migrations applied and app engines pointed at it."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", ephemeral_database)
    command.upgrade(cfg, "head")

    test_url_async = ephemeral_database.replace("postgresql+psycopg://", "postgresql+asyncpg://")

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", test_url_async)
    monkeypatch.setattr(settings, "database_url_sync", ephemeral_database)
    _clear_db_engine_caches()

    yield ephemeral_database

    # `monkeypatch` restores the Settings attributes; clear caches so the
    # next test starts with engines that match whatever the next test sets.
    _clear_db_engine_caches()


@pytest.fixture
def synthetic_prices_df() -> pd.DataFrame:
    """30 weekday bars of synthetic OHLCV for ticker `0700.HK`, schema-clean."""
    end = date.today() - timedelta(days=1)
    dates = pd.bdate_range(end=pd.Timestamp(end), periods=30)
    df = pd.DataFrame(
        {
            "provider": pd.array(["yfinance"] * 30, dtype="string"),
            "ticker": pd.array(["0700.HK"] * 30, dtype="string"),
            "date": dates,
            "open": 400.0,
            "high": 410.0,
            "low": 395.0,
            "close": 405.0,
            "adjusted_close": 405.0,
            "volume": pd.array([1_000_000] * 30, dtype="Int64"),
        }
    )
    return df
