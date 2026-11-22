"""FastAPI application factory. Run with ``uvicorn --factory app.main:create_app``."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.db.session import create_engine, create_sessionmaker
from app.logging import RequestIdMiddleware, configure_logging
from app.settings import get_settings
from app.workers import queue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_engine(get_settings())
    app.state.sessionmaker = create_sessionmaker(engine)
    try:
        async with queue.app.open_async():
            yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    # Docs and the OpenAPI spec stay off in prod (the public ingress must not show them).
    docs = settings.env != "prod"
    app = FastAPI(
        title="Flaky Test Quarantine",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.include_router(health.router)
    # Added last = outermost: the request ID is bound before anything else logs.
    app.add_middleware(health.MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app
