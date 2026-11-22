import json
import logging
from collections.abc import Iterator

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.settings import get_settings


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Lets a test change FQ_* values; get_settings() is cached, so clear it around the test."""
    get_settings.cache_clear()
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield monkeypatch
    get_settings.cache_clear()
    structlog.reset_defaults()
    root.handlers[:], root.level = saved_handlers, saved_level


async def _get(path: str, **headers: str) -> tuple[int, dict[str, str]]:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as http:
        response = await http.get(path, headers=headers)
    return response.status_code, dict(response.headers)


async def test_ci_logs_are_json_with_request_id(
    env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env.setenv("FQ_ENV", "ci")

    _, headers = await _get("/healthz")

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["event"] == "request_completed"
    assert line["request_id"] == headers["x-request-id"]
    assert line["path"] == "/healthz"
    assert line["status"] == 200


async def test_local_logs_are_readable_not_json(
    env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env.setenv("FQ_ENV", "local")

    await _get("/healthz")

    out = capsys.readouterr().out
    assert "request_completed" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip().splitlines()[-1])


async def test_valid_incoming_request_id_is_kept(env: pytest.MonkeyPatch) -> None:
    env.setenv("FQ_ENV", "ci")

    _, headers = await _get("/healthz", **{"X-Request-ID": "abc-123"})

    assert headers["x-request-id"] == "abc-123"


@pytest.mark.parametrize("bad", ["has space", "x" * 65, "line\\nbreak", '{"a":1}'])
async def test_invalid_incoming_request_id_is_replaced(env: pytest.MonkeyPatch, bad: str) -> None:
    env.setenv("FQ_ENV", "ci")

    _, headers = await _get("/healthz", **{"X-Request-ID": bad})

    assert headers["x-request-id"] != bad
    assert len(headers["x-request-id"]) == 32


async def test_unhandled_error_is_logged_as_500_with_request_id(
    env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env.setenv("FQ_ENV", "ci")
    app = create_app()

    async def boom() -> None:
        raise RuntimeError("boom")

    app.add_api_route("/boom", boom)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as http:
        response = await http.get("/boom")

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert response.status_code == 500
    assert (line["event"], line["status"], line["path"]) == ("request_completed", 500, "/boom")
    assert len(line["request_id"]) == 32


def test_ci_library_logs_are_json_too(
    env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env.setenv("FQ_ENV", "ci")
    create_app()

    logging.getLogger("procrastinate.worker").warning("worker_started")

    line = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert (line["event"], line["level"], line["logger"]) == (
        "worker_started",
        "warning",
        "procrastinate.worker",
    )
