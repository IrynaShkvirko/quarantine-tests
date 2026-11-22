"""install procrastinate schema

The job queue's tables, functions and types are a frozen copy of the SQL that Procrastinate
shipped when this migration was written (a1f4c0d2b7e9_procrastinate_schema.sql), so a fresh
database always gets the same schema whatever version is installed. Upgrading Procrastinate later
needs its own migration (``procrastinate schema --migrate`` has the SQL).

Revision ID: a1f4c0d2b7e9
Revises: cb650922192f
Create Date: 2026-11-22 16:05:00.000000
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "a1f4c0d2b7e9"
down_revision: str | None = "cb650922192f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA_SQL = (Path(__file__).parent / "a1f4c0d2b7e9_procrastinate_schema.sql").read_text()

_DROP_ALL = """
DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers,
    procrastinate_jobs, procrastinate_workers CASCADE;
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT p.oid::regprocedure AS signature FROM pg_proc p
        WHERE p.pronamespace = current_schema()::regnamespace
          AND p.proname LIKE 'procrastinate\\_%'
    LOOP
        EXECUTE 'DROP FUNCTION ' || r.signature;
    END LOOP;
END $$;
DROP TYPE IF EXISTS procrastinate_job_to_defer_v2, procrastinate_job_status,
    procrastinate_job_event_type, procrastinate_lock_mode;
"""


def _run_raw(sql: str) -> None:
    # The SQL contains PL/pgSQL `RAISE '...%'` and `format('%I')`. text() would read colons as
    # binds, and psycopg reads a bare `%` as a placeholder, so go to the driver with `%%`.
    op.get_bind().exec_driver_sql(sql.replace("%", "%%"))


def upgrade() -> None:
    # shortcut: skips when the tables exist, because M0-05 databases got the schema from a
    # runtime installer; drop this guard once no such database is left.
    exists = op.get_bind().exec_driver_sql("SELECT to_regclass('procrastinate_jobs')").scalar()
    if exists is None:
        _run_raw(_SCHEMA_SQL)


def downgrade() -> None:
    _run_raw(_DROP_ALL)
