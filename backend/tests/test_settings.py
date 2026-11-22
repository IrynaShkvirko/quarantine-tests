import pytest
from pydantic import ValidationError

from app.settings import Settings, get_settings

_URL = "postgresql+psycopg://u:p@db:5432/fq"


def test_reads_fq_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", _URL)
    monkeypatch.setenv("FQ_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("FQ_ENV", "ci")
    monkeypatch.setenv("FQ_INGEST_MAX_UPLOAD_MB", "7")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.log_level == "DEBUG"
    assert settings.env == "ci"
    assert settings.ingest_max_upload_mb == 7


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", _URL)
    for name in ("FQ_LOG_LEVEL", "FQ_ENV", "FQ_INGEST_MAX_UPLOAD_MB"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()  # type: ignore[call-arg]

    assert settings.log_level == "INFO"
    assert settings.env == "local"
    assert settings.ingest_max_upload_mb == 50


def test_env_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", _URL)
    monkeypatch.setenv("FQ_ENV", "dev")

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_psycopg_dsn_drops_sqlalchemy_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", _URL)

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


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


@pytest.mark.parametrize("url", ["postgresql://u:p@db/fq", "mysql://u:p@db/fq", "x"])
def test_database_url_must_use_the_psycopg_driver(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("FQ_DATABASE_URL", url)

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
