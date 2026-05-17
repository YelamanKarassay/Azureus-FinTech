"""SQLAlchemy declarative base, metadata, and engine/session factories.

Alembic uses `metadata` (with our naming convention) to generate predictable
constraint and index names. API routes and worker tasks use the engine and
sessionmaker factories below.

Engines are constructed lazily on first access so importing this module
never fails on environments where `DATABASE_URL` is unset (CI without a
running Postgres, ad-hoc shells, etc.). Once constructed they're cached
for process lifetime.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from azureus.config import get_settings

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy declarative base.

    All ORM models inherit from this. Reuses the shared `metadata` so Alembic
    sees every model under one `MetaData` object.
    """

    metadata = metadata


def _require(value: str, env_var: str) -> str:
    if not value:
        raise RuntimeError(
            f"{env_var} is not set. Copy .env.example to .env or export the variable."
        )
    return value


@lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    """Lazy async engine using asyncpg — used by FastAPI handlers and async workers."""
    settings = get_settings()
    url = _require(settings.database_url, "DATABASE_URL")
    return create_async_engine(url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_sync_engine() -> Engine:
    """Lazy sync engine using psycopg — used by Alembic, RQ workers, and Prefect flows."""
    settings = get_settings()
    url = _require(settings.database_url_sync, "DATABASE_URL_SYNC")
    return create_engine(url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_async_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


@lru_cache(maxsize=1)
def get_sync_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_sync_engine(),
        class_=Session,
        expire_on_commit=False,
    )


@asynccontextmanager
async def async_session() -> AsyncIterator[AsyncSession]:
    """Convenience context manager — commits on success, rolls back on exception."""
    factory = get_async_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextmanager
def sync_session() -> Iterator[Session]:
    """Convenience context manager — commits on success, rolls back on exception."""
    factory = get_sync_sessionmaker()
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
