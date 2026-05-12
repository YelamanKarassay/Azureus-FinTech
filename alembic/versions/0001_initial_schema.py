"""Initial schema — Phase 1 §3.5 tables, hypertables, and indexes.

Revision ID: 0001
Revises:
Create Date: 2026-05-12

Creates the 9 Phase 1 tables (tickers, prices, macro_series, fundamentals_pit,
universe_membership, strategies, jobs, backtest_results, ingestion_runs).

Converts `prices` and `macro_series` into TimescaleDB hypertables via raw SQL
(`op.execute`) since Alembic autogenerate doesn't handle TimescaleDB DDL.

Indexes from §3.6 included: PIT fundamentals composite query-path with
INCLUDE clause, universe membership lookup, jobs active-status partial,
tickers sector lookup, ingestion lineage recent-runs.

`feature_cache` (also a §3.5 hypertable) is deferred to a later migration —
its column set depends on feature-engineering work (Phase 3).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # ---- tickers (reference, parent of multiple FKs) ----
    op.create_table(
        "tickers",
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="HKD"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("listed_date", sa.Date(), nullable=True),
        sa.Column("delisted_date", sa.Date(), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("ticker", name="pk_tickers"),
    )
    op.create_index("ix_tickers_sector", "tickers", ["sector"])

    # ---- strategies (parent of jobs FK) ----
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_strategies"),
    )

    # ---- prices (TimescaleDB hypertable on `date`) ----
    op.create_table(
        "prices",
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("high", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("low", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("close", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("adjusted_close", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("provider", "ticker", "date", name="pk_prices"),
        sa.ForeignKeyConstraint(
            ["ticker"], ["tickers.ticker"], name="fk_prices_ticker_tickers"
        ),
    )
    # Autogenerate can't issue this; raw SQL via op.execute.
    op.execute(
        "SELECT create_hypertable('prices', 'date', "
        "if_not_exists => TRUE, migrate_data => TRUE)"
    )

    # ---- macro_series (TimescaleDB hypertable on `date`) ----
    op.create_table(
        "macro_series",
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("series_id", sa.String(length=64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("reported_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("provider", "series_id", "date", name="pk_macro_series"),
    )
    op.execute(
        "SELECT create_hypertable('macro_series', 'date', "
        "if_not_exists => TRUE, migrate_data => TRUE)"
    )

    # ---- fundamentals_pit (plain Postgres; sparse, ticker-keyed) ----
    op.create_table(
        "fundamentals_pit",
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("reported_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column(
            "is_restated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "provider",
            "ticker",
            "metric",
            "period_end",
            "reported_date",
            name="pk_fundamentals_pit",
        ),
        sa.ForeignKeyConstraint(
            ["ticker"], ["tickers.ticker"], name="fk_fundamentals_pit_ticker_tickers"
        ),
    )
    # Composite index with DESC ordering + INCLUDE clause for index-only scans
    # (the PIT query path: `WHERE ticker=? AND metric=? AND reported_date <= ?`).
    op.execute(
        "CREATE INDEX ix_fundamentals_pit_query_path "
        "ON fundamentals_pit (ticker, metric, reported_date DESC, provider) "
        "INCLUDE (value)"
    )

    # ---- universe_membership (interval table) ----
    op.create_table(
        "universe_membership",
        sa.Column("index_id", sa.String(length=32), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("weight_at_entry", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.PrimaryKeyConstraint(
            "index_id", "ticker", "start_date", name="pk_universe_membership"
        ),
        sa.ForeignKeyConstraint(
            ["ticker"],
            ["tickers.ticker"],
            name="fk_universe_membership_ticker_tickers",
        ),
    )
    op.create_index(
        "ix_universe_membership_lookup",
        "universe_membership",
        ["index_id", "start_date", "end_date"],
    )

    # ---- jobs ----
    op.create_table(
        "jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("strategy_id", sa.String(length=64), nullable=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("code_version", sa.String(length=64), nullable=False),
        sa.Column("dependencies_lock", sa.Text(), nullable=True),
        sa.Column("git_status_clean", sa.Boolean(), nullable=False),
        sa.Column("as_of_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_provider", sa.String(length=16), nullable=False),
        sa.Column(
            "mlflow_run_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], name="fk_jobs_strategy_id_strategies"
        ),
    )
    op.create_index(
        "ix_jobs_active",
        "jobs",
        ["created_at"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    # ---- backtest_results (CASCADE on job delete) ----
    op.create_table(
        "backtest_results",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "equity_curve", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("holdings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trades", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("job_id", name="pk_backtest_results"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_backtest_results_job_id_jobs",
            ondelete="CASCADE",
        ),
    )

    # ---- ingestion_runs (lineage) ----
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pipeline_name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("table_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_runs"),
    )
    op.execute(
        "CREATE INDEX ix_ingestion_runs_recent "
        "ON ingestion_runs (pipeline_name, started_at DESC)"
    )


def downgrade() -> None:
    # Drop in reverse dependency order. Dropping a TimescaleDB hypertable via
    # standard DROP TABLE also cleans up the TS catalog automatically.
    op.execute("DROP INDEX IF EXISTS ix_ingestion_runs_recent")
    op.drop_table("ingestion_runs")
    op.drop_table("backtest_results")
    op.drop_index("ix_jobs_active", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_universe_membership_lookup", table_name="universe_membership")
    op.drop_table("universe_membership")
    op.execute("DROP INDEX IF EXISTS ix_fundamentals_pit_query_path")
    op.drop_table("fundamentals_pit")
    op.drop_table("macro_series")
    op.drop_table("prices")
    op.drop_table("strategies")
    op.drop_index("ix_tickers_sector", table_name="tickers")
    op.drop_table("tickers")
    # Leave timescaledb extension installed — it's a global Postgres feature
    # and future migrations or other tools may depend on it.
