"""Smoke tests for sync and async DB session factories.

Verifies both psycopg (sync) and asyncpg (async) drivers can reach the
configured Postgres instance and return a basic result. Auto-skips when
`DATABASE_URL_SYNC` is unset so CI without Postgres stays green.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from azureus.config import get_settings
from azureus.data.db import async_session, sync_session


def _skip_without_db() -> None:
    settings = get_settings()
    if not settings.database_url_sync or not settings.database_url:
        pytest.skip("DATABASE_URL / DATABASE_URL_SYNC not set — skipping DB smoke tests")


def test_sync_session_connects_and_queries() -> None:
    _skip_without_db()
    with sync_session() as session:
        result = session.execute(text("SELECT 1")).scalar_one()
    assert result == 1


async def test_async_session_connects_and_queries() -> None:
    _skip_without_db()
    async with async_session() as session:
        result = (await session.execute(text("SELECT 1"))).scalar_one()
    assert result == 1


def test_sync_session_sees_timescaledb_extension() -> None:
    """Sanity-check: the migrated DB has timescaledb available via the sync engine."""
    _skip_without_db()
    with sync_session() as session:
        ext = session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
        ).scalar_one_or_none()
    assert ext == "timescaledb", "timescaledb extension missing — run alembic upgrade head"
