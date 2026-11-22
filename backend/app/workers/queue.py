"""Procrastinate application. Run the worker with ``python -m app worker``."""

from procrastinate import App, PsycopgConnector

from app.settings import get_settings

app = App(connector=PsycopgConnector(conninfo=get_settings().psycopg_dsn))


@app.task(name="ping")
def ping() -> str:
    """Only used by tests to prove a deferred task reaches a worker."""
    return "pong"
