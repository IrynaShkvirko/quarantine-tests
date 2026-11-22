"""Install the Procrastinate queue schema once; later runs are no-ops.

Run after ``alembic upgrade head`` by the ``migrate`` entrypoint. Queue schema upgrades
across Procrastinate versions are a follow-up (``procrastinate schema --migrate``).
"""

import psycopg
from procrastinate import App, PsycopgConnector

from app.settings import get_settings

# Arbitrary constant: concurrent runs serialise on it instead of both installing the schema.
_LOCK_KEY = 7_340_001
_CHECK_SQL = "SELECT to_regclass('procrastinate_jobs') IS NOT NULL"


def main() -> None:
    dsn = get_settings().psycopg_dsn
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
        row = conn.execute(_CHECK_SQL).fetchone()
        if row is not None and row[0]:
            print("procrastinate schema already installed")
            return
        queue = App(connector=PsycopgConnector(conninfo=dsn))
        with queue.open():
            queue.schema_manager.apply_schema()
        print("procrastinate schema installed")
    # The lock is session-level: closing the connection releases it.


if __name__ == "__main__":
    main()
