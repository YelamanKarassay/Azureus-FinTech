"""Migration tests — verify the initial schema applies, rolls back, and re-applies cleanly.

The `ephemeral_database` fixture is defined in `tests/conftest.py`. Tests are
skipped automatically when `DATABASE_URL_SYNC` is unset (CI without Postgres).
"""

from __future__ import annotations

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command

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


def _alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


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
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'backtest_results'"
                )
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
    assert "diagnostics" in columns


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
