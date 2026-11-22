"""``/healthz`` (liveness), ``/readyz`` (readiness) and ``/metrics`` (Prometheus)."""

import asyncio
import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.db.session import get_session

router = APIRouter()
logger = structlog.get_logger()

REQUESTS = Counter("fq_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("fq_http_request_duration_seconds", "HTTP request latency", ["method", "route"])

_QUEUE_SCHEMA_SQL = text("SELECT to_regclass('procrastinate_jobs') IS NOT NULL")
# Unrouted requests (404s from scanners) share one label so they cannot blow up cardinality.
_READY_TIMEOUT_S = 2
_UNMATCHED = "unmatched"
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: Annotated[AsyncSession, Depends(get_session)]) -> Response:
    try:
        async with asyncio.timeout(_READY_TIMEOUT_S):  # a stalled database must not hang probes
            queue_ready = (await session.execute(_QUEUE_SCHEMA_SQL)).scalar_one()
    except (SQLAlchemyError, TimeoutError) as exc:
        logger.warning("readyz_failed", reason="database_unreachable", error=type(exc).__name__)
        return JSONResponse({"status": "unavailable", "reason": "database"}, status_code=503)
    if not queue_ready:
        logger.warning("readyz_failed", reason="queue_schema_missing")
        return JSONResponse({"status": "unavailable", "reason": "queue_schema"}, status_code=503)
    return JSONResponse({"status": "ok"})


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class MetricsMiddleware:
    """Counts requests and times them, labelled by route template (``/tests/{id}``)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status = 500
        started = time.perf_counter()

        async def send_capturing_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_capturing_status)
        finally:
            # The router stores the matched route in the scope while handling the request.
            route = getattr(scope.get("route"), "path", _UNMATCHED)
            method = scope["method"] if scope["method"] in _METHODS else "OTHER"
            REQUESTS.labels(method, route, str(status)).inc()
            LATENCY.labels(method, route).observe(time.perf_counter() - started)
