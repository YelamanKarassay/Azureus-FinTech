"""Alembic migration environment.

Loads the sync database URL from `azureus.config.get_settings()` (which reads
`DATABASE_URL_SYNC` from process env / `.env`) and runs migrations against
`azureus.data.db.metadata`.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from azureus.config import get_settings
from azureus.data import models  # noqa: F401  -- import populates metadata
from azureus.data.db import metadata as target_metadata

config = context.config

# Prefer a URL the caller already set on the Config (e.g. the migration test
# pointing at an ephemeral DB). Fall back to `DATABASE_URL_SYNC` from env
# only if the caller left the alembic.ini placeholder in place.
_PLACEHOLDER_URL = "driver://user:pass@localhost/dbname"
_existing_url = config.get_main_option("sqlalchemy.url") or ""
if not _existing_url or _existing_url == _PLACEHOLDER_URL:
    settings = get_settings()
    if not settings.database_url_sync:
        raise RuntimeError(
            "DATABASE_URL_SYNC must be set (via .env or process env) to run Alembic. "
            "Example: postgresql+psycopg://azureus:changeme@localhost:5432/azureus"
        )
    config.set_main_option("sqlalchemy.url", settings.database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Emit SQL to script output without a live DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and execute migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
