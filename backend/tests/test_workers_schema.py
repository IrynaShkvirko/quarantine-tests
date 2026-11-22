import os
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from app.workers import schema

pytestmark = pytest.mark.integration

_SCRATCH_DB = "fq_schema_scratch"


def _with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


@pytest.fixture
def scratch_dsn() -> Iterator[str]:
    """An empty throwaway database on the compose Postgres (needs `make up` and the .env values)."""
    admin_url = os.environ["FQ_DATABASE_URL"].replace("+psycopg", "", 1)
    name = sql.Identifier(_SCRATCH_DB)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(name))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(name))
    try:
        yield _with_database(admin_url, _SCRATCH_DB)
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(name))


def test_installs_once_and_is_a_no_op_the_second_time(
    scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", scratch_dsn)

    schema.main()
    schema.main()

    out = capsys.readouterr().out.splitlines()
    assert out == ["procrastinate schema installed", "procrastinate schema already installed"]
