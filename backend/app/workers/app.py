"""Procrastinate application. Run with ``procrastinate --app=app.workers.app.app worker``."""

from procrastinate import App, PsycopgConnector

from app.settings import get_settings

app = App(connector=PsycopgConnector(conninfo=get_settings().psycopg_dsn))
