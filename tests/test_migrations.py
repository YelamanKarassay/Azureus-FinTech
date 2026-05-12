"""Migration tests — verify the initial schema applies, rolls back, and re-applies cleanly.

Requires a running Postgres+TimescaleDB instance with `DATABASE_URL_SYNC` set
in the environment (loaded from `.env` via `azureus.config.get_settings()`).
Skipped if the env var is empty, so the rest of the test suite stays green
in CI environments without Postgres.

Each test provisions a uniquely-named ephemeral database against the existing
Postgres server (the docker-compose container locally) and drops it after.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from azureus.config import get_settings

REQUIRED_TABLES = {
    "tickers",
    "prices",
    "macro_series",
    "fundamentals_pit",
    "universe_membership",
    "strategies",
    "jobs",
    "backtest_results",
    "ingestion_runs",
}

REQUIRED_HYPERTABLES = {"prices", "macro_series"}

REQUIRED_INDEXES = {
    "ix_tickers_sector",
    "ix_fundamentals_pit_query_path",
    "ix_universe_membership_lookup",
    "ix_jobs_active",
    "ix_ingestion_runs_recent",
}


def _split_server_and_db(url: str) -> tuple[str, str]:
    """Split a Postgres URL into (server-prefix, database-name)."""
    server, db = url.rsplit("/", 1)
    return server, db


def _alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def ephemeral_database() -> Iterator[str]:
    """Provision a uniquely-named test database; drop it after the test."""
    settings = get_settings()
    if not settings.database_url_sync:
        pytest.skip("DATABASE_URL_SYNC not set — skipping migration tests")

    server_url, _ = _split_server_and_db(settings.database_url_sync)
    test_db = f"test_azureus_{uuid.uuid4().hex[:8]}"
    test_url = f"{server_url}/{test_db}"
    admin_url = f"{server_url}/postgres"

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{test_db}"'))

    # Pre-install timescaledb in the new DB using autocommit. The migration
    # also runs `CREATE EXTENSION IF NOT EXISTS`, but doing it here outside
    # any transaction guarantees the extension is fully usable before
    # Alembic's transactional DDL starts — TimescaleDB doesn't reliably
    # install in the same transaction that then calls `create_hypertable`.
    bootstrap_engine = create_engine(test_url, isolation_level="AUTOCOMMIT")
    with bootstrap_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    bootstrap_engine.dispose()

    try:
        yield test_url
    finally:
        with admin_engine.connect() as conn:
            # Terminate lingering connections so DROP DATABASE doesn't block.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": test_db},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db}"'))
        admin_engine.dispose()


def test_migration_creates_full_schema(ephemeral_database: str) -> None:
    """Upgrade-from-empty creates every expected table, hypertable, and index."""
    cfg = _alembic_config(ephemeral_database)
    command.upgrade(cfg, "head")

    engine = create_engine(ephemeral_database)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
        hypertables = {
            row[0]
            for row in conn.execute(
                text("SELECT hypertable_name FROM timescaledb_information.hypertables")
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            )
        }
    engine.dispose()

    missing_tables = REQUIRED_TABLES - tables
    assert not missing_tables, f"missing tables: {missing_tables}"

    assert hypertables == REQUIRED_HYPERTABLES, (
        f"hypertable mismatch — got {hypertables}, expected {REQUIRED_HYPERTABLES}"
    )

    missing_indexes = REQUIRED_INDEXES - indexes
    assert not missing_indexes, f"missing indexes: {missing_indexes}"


def test_migration_is_reversible(ephemeral_database: str) -> None:
    """`downgrade base` drops everything we created."""
    cfg = _alembic_config(ephemeral_database)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(ephemeral_database)
    with engine.connect() as conn:
        remaining = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
    engine.dispose()

    # alembic_version may persist with no row; everything else must be gone.
    leftover = remaining - {"alembic_version"}
    assert leftover == set(), f"tables still exist after downgrade: {leftover}"


def test_migration_re_applies_after_downgrade(ephemeral_database: str) -> None:
    """Round-trip up → down → up succeeds (covers idempotency of the hypertable DDL)."""
    cfg = _alembic_config(ephemeral_database)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    engine = create_engine(ephemeral_database)
    with engine.connect() as conn:
        hypertables = {
            row[0]
            for row in conn.execute(
                text("SELECT hypertable_name FROM timescaledb_information.hypertables")
            )
        }
    engine.dispose()
    assert hypertables == REQUIRED_HYPERTABLES
