import psycopg
import pytest
from tests.conftest import migrate

pytestmark = pytest.mark.integration

_QUEUE_TABLE = "SELECT to_regclass('procrastinate_jobs') IS NOT NULL"


def _queue_installed(database_url: str) -> bool:
    with psycopg.connect(database_url.replace("+psycopg", "", 1)) as conn:
        row = conn.execute(_QUEUE_TABLE).fetchone()
    assert row is not None
    return bool(row[0])


def test_upgrade_head_then_downgrade_base_on_an_empty_database(scratch_database_url: str) -> None:
    migrate(scratch_database_url)
    assert _queue_installed(scratch_database_url)

    migrate(scratch_database_url, "base", downgrade=True)
    assert not _queue_installed(scratch_database_url)

    migrate(scratch_database_url)  # and back up again
    assert _queue_installed(scratch_database_url)
