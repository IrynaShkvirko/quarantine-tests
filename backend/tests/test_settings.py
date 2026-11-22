import pytest
from pydantic import ValidationError

from app.settings import Settings


def test_reads_fq_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/fq")
    monkeypatch.setenv("FQ_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("FQ_ENV", "test")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.log_level == "DEBUG"
    assert settings.env == "test"


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/fq")
    monkeypatch.delenv("FQ_LOG_LEVEL", raising=False)
    monkeypatch.delenv("FQ_ENV", raising=False)

    settings = Settings()  # type: ignore[call-arg]

    assert settings.log_level == "INFO"
    assert settings.env == "dev"


def test_psycopg_dsn_drops_sqlalchemy_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/fq")

    assert Settings().psycopg_dsn == "postgresql://u:p@db:5432/fq"  # type: ignore[call-arg]


def test_database_url_password_is_not_exposed_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", "postgresql+psycopg://u:s3cret@db:5432/fq")

    settings = Settings()  # type: ignore[call-arg]

    assert "s3cret" not in repr(settings)
    assert settings.sqlalchemy_url == "postgresql+psycopg://u:s3cret@db:5432/fq"


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FQ_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
