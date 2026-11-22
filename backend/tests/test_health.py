import asyncio
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from procrastinate import PsycopgConnector
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import app_client, session_for

from app.main import create_app
from app.settings import get_settings
from app.workers import queue


async def test_healthz_is_ok_without_a_database(bare_client: AsyncClient) -> None:
    response = await bare_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_is_503_when_the_database_is_down() -> None:
    engine = create_async_engine("postgresql+psycopg://u:p@127.0.0.1:1/x")  # port 1 refuses

    async with app_client(session_for(engine)) as http:
        response = await http.get("/readyz")
    await engine.dispose()

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "reason": "database"}


async def test_readyz_is_503_when_the_database_stalls(monkeypatch: pytest.MonkeyPatch) -> None:
    class StalledSession:
        async def execute(self, *_args: object) -> None:
            await asyncio.sleep(10)

    async def stalled() -> AsyncIterator[StalledSession]:
        yield StalledSession()

    monkeypatch.setattr("app.api.health._READY_TIMEOUT_S", 0.01)

    async with app_client(stalled) as http:
        response = await http.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "reason": "database"}


async def test_metrics_expose_request_count_and_latency_by_route(bare_client: AsyncClient) -> None:
    await bare_client.get("/healthz")
    await bare_client.get("/no-such-path")

    body = (await bare_client.get("/metrics")).text

    assert 'fq_http_requests_total{method="GET",route="/healthz",status="200"}' in body
    assert 'fq_http_request_duration_seconds_count{method="GET",route="/healthz"}' in body
    # Unknown paths share one label instead of creating a series per path.
    assert 'route="unmatched",status="404"' in body
    assert "/no-such-path" not in body


async def test_unknown_http_methods_share_one_metrics_label(bare_client: AsyncClient) -> None:
    await bare_client.request("BREW", "/healthz")

    body = (await bare_client.get("/metrics")).text

    assert 'method="OTHER"' in body
    assert "BREW" not in body


async def test_prod_hides_api_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FQ_ENV", "prod")
    get_settings.cache_clear()
    async with app_client() as http:
        docs, spec = await http.get("/docs"), await http.get("/openapi.json")
    get_settings.cache_clear()

    assert (docs.status_code, spec.status_code) == (404, 404)


@pytest.mark.integration
async def test_readyz_is_ok_when_database_and_queue_schema_exist(client: AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
async def test_readyz_is_503_when_the_queue_schema_is_missing(scratch_database_url: str) -> None:
    engine = create_async_engine(scratch_database_url)  # empty database: no Procrastinate tables

    async with app_client(session_for(engine)) as http:
        response = await http.get("/readyz")
    await engine.dispose()

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "reason": "queue_schema"}


@pytest.mark.integration
async def test_lifespan_wires_the_real_session_and_queue(
    test_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", test_database_url)
    get_settings.cache_clear()
    app = create_app()
    # queue.app was built at import from the default URL, so point it at fq_test for this test.
    connector = PsycopgConnector(conninfo=test_database_url.replace("+psycopg", "", 1))
    with queue.app.replace_connector(connector):
        async with app.router.lifespan_context(app):
            from httpx import ASGITransport

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
                response = await http.get("/readyz")
    get_settings.cache_clear()

    assert response.status_code == 200
