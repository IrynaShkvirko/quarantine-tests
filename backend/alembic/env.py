import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.db.models  # noqa: F401  registers every table on Base.metadata
from app.db.base import Base, include_object
from app.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    # Tests point Alembic at a scratch database through config.attributes; everything else
    # (CLI, compose, CI) uses FQ_DATABASE_URL.
    return config.attributes.get("database_url") or get_settings().sqlalchemy_url


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, include_object=include_object
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit(
        "offline mode (--sql) is not supported: the queue migration needs a connection"
    )
asyncio.run(run_migrations_online())
