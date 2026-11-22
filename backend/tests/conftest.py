import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

# Same value as .env.example. Must be set before `app.workers.queue` is imported; unit tests
# never connect with it.
os.environ.setdefault(
    "FQ_DATABASE_URL", "postgresql+psycopg://fq:fq-local-password@localhost:5433/fq"
)

from app.db.session import get_session
from app.main import create_app
from app.settings import get_settings

_BACKEND = Path(__file__).resolve().parents[1]
_TEST_DB = "fq_test"
_SCRATCH_DB = "fq_scratch"


def _url_for(database: str) -> str:
    parts = urlsplit(get_settings().sqlalchemy_url)
    return urlunsplit(parts._replace(path=f"/{database}"))


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db"}


def _recreate_database(database: str) -> None:
    host = urlsplit(get_settings().sqlalchemy_url).hostname
    if host not in _LOCAL_HOSTS:
        pytest.exit(f"refusing to DROP DATABASE {database} on non-local host {host!r}", 2)
    admin_dsn = get_settings().psycopg_dsn
    name = sql.Identifier(database)
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(name))


def migrate(database_url: str, revision: str = "head", *, downgrade: bool = False) -> None:
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    config.attributes["database_url"] = database_url
    (command.downgrade if downgrade else command.upgrade)(config, revision)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """A fresh `fq_test` migrated to head. Needs `make up` (or the CI Postgres service)."""
    _recreate_database(_TEST_DB)
    url = _url_for(_TEST_DB)
    migrate(url)
    return url


@pytest.fixture
def scratch_database_url() -> Iterator[str]:
    """An empty throwaway database, for tests that migrate up and down."""
    _recreate_database(_SCRATCH_DB)
    yield _url_for(_SCRATCH_DB)
    with psycopg.connect(get_settings().psycopg_dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(_SCRATCH_DB))
        )


@pytest.fixture
async def session(test_database_url: str) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back after the test."""
    engine = create_async_engine(test_database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # Savepoints let code under test call commit() without ending the outer transaction.
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as db_session:
            yield db_session
        await transaction.rollback()
    await engine.dispose()


@asynccontextmanager
async def app_client(
    session_dependency: Callable[[], object] | None = None,
) -> AsyncIterator[AsyncClient]:
    """The app behind an httpx client; `get_session` can be replaced. Lifespan is not run."""
    app = create_app()
    if session_dependency is not None:
        app.dependency_overrides[get_session] = session_dependency
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        yield http


def session_for(engine: AsyncEngine) -> Callable[[], AsyncIterator[AsyncSession]]:
    async def dependency() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine) as db_session:
            yield db_session

    return dependency


@pytest.fixture
async def bare_client() -> AsyncIterator[AsyncClient]:
    """The app without a database."""
    async with app_client() as http:
        yield http


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async with app_client(lambda: session) as http:
        yield http
