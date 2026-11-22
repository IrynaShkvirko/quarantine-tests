"""Async engine, session factory and the per-request session dependency."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.settings import Settings

# Fail fast when the database is down, so /readyz answers 503 instead of hanging.
_CONNECT_TIMEOUT_S = 3


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_S},
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Callers commit; an unhandled error rolls back on close."""
    async with request.app.state.sessionmaker() as session:
        yield session
