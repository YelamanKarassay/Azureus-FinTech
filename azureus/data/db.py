"""SQLAlchemy declarative base and shared `MetaData` with naming convention.

Alembic generates predictable index / FK / constraint names from this
convention instead of opaque auto-generated ones — important when migrations
are diffed or rewritten.

Async engine and session factories are added when API routes start touching
the database (Phase 3). For now this module exposes only what Alembic and
the migration test need.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

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
