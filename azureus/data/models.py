"""SQLAlchemy ORM models — implements docs/ARCHITECTURE.md §3.5 schema.

Provider isolation is enforced via a `provider` column on time-series tables
(included in the primary key). Strategies must query through the `DataSource`
interface (§3.4) — never these models directly.

`feature_cache` (also a §3.5 hypertable) is deferred to a later migration;
its column set depends on feature-engineering decisions in Phase 3.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from azureus.data.db import Base


class Ticker(Base):
    """Reference table for every ticker we know about (HK equities + later markets)."""

    __tablename__ = "tickers"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(128))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HKD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    listed_date: Mapped[dt.date | None] = mapped_column(Date)
    delisted_date: Mapped[dt.date | None] = mapped_column(Date)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index("ix_tickers_sector", "sector"),)


class Price(Base):
    """Daily OHLCV bars. TimescaleDB hypertable partitioned by `date`.

    Adjusted close (corporate-action-adjusted) is the canonical price column
    for return calculations; raw OHLC are retained for reference.
    """

    __tablename__ = "prices"

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("tickers.ticker", name="fk_prices_ticker_tickers"),
        primary_key=True,
    )
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MacroSeries(Base):
    """Macro features (USD/HKD, HIBOR, oil, gold, VIX, US 10Y, etc.).

    PIT-correct: stores both value-date (`date`) and `reported_date` (the date
    the value became publicly known). Hypertable partitioned by `date`.
    """

    __tablename__ = "macro_series"

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    series_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    reported_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FundamentalPIT(Base):
    """Point-in-time fundamentals, long-format (one row per metric).

    `reported_date` is part of the primary key so restatements are preserved
    as separate rows. Strategy queries filter `reported_date <= as_of_date`.
    Plain Postgres table (sparse, ticker-keyed) — not a hypertable.
    """

    __tablename__ = "fundamentals_pit"

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("tickers.ticker", name="fk_fundamentals_pit_ticker_tickers"),
        primary_key=True,
    )
    metric: Mapped[str] = mapped_column(String(64), primary_key=True)
    period_end: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    reported_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    unit: Mapped[str | None] = mapped_column(String(16))
    is_restated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # PIT query-path index built in raw SQL in the migration to include
    # `reported_date DESC` ordering plus an INCLUDE (value) clause for
    # index-only scans — SQLAlchemy's Index() helper can't express both.


class UniverseMembership(Base):
    """Interval table mapping (index, ticker) to membership periods.

    `end_date IS NULL` ⇒ still a member. Strategy code queries via
    `DataSource.get_universe(index_id, as_of_date)` — never directly.
    """

    __tablename__ = "universe_membership"

    index_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("tickers.ticker", name="fk_universe_membership_ticker_tickers"),
        primary_key=True,
    )
    start_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    weight_at_entry: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))

    __table_args__ = (Index("ix_universe_membership_lookup", "index_id", "start_date", "end_date"),)


class Strategy(Base):
    """Strategy registry — minimal metadata; strategy logic lives in code."""

    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(32), nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Job(Base):
    """Execution log for backtests, training runs, and ingestion.

    Mandatory reproducibility fields per §3.10: `code_version`,
    `dependencies_lock`, `git_status_clean`, `as_of_timestamp`,
    `data_provider`, and explicit random seeds embedded in `params`.
    """

    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    strategy_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("strategies.id", name="fk_jobs_strategy_id_strategies"),
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    code_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dependencies_lock: Mapped[str | None] = mapped_column(Text)
    git_status_clean: Mapped[bool] = mapped_column(Boolean, nullable=False)
    as_of_timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_provider: Mapped[str] = mapped_column(String(16), nullable=False)

    mlflow_run_ids: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    # Partial index on active statuses built in the migration; SQLAlchemy's
    # Index() does support `postgresql_where=` but the migration writes raw
    # SQL alongside other partial indexes for consistency.


class BacktestResult(Base):
    """Result payload for a backtest job. Columns split per §5.3 so views can
    fetch just the slice they need (e.g. equity curve only, holdings only).
    """

    __tablename__ = "backtest_results"

    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs.id", name="fk_backtest_results_job_id_jobs", ondelete="CASCADE"),
        primary_key=True,
    )
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    equity_curve: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    holdings: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    trades: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IngestionRun(Base):
    """Lineage row written by every ingestion pipeline run (§3.7).

    Failures are recorded with full context in `errors`. No silent swallows
    (per CLAUDE.md "Common Mistakes" #9).
    """

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pipeline_name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    table_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    rows_inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    errors: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
