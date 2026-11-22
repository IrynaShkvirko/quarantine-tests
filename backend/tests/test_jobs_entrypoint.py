import pytest

from app.jobs.__main__ import main


def test_unknown_job_exits_with_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["nope"]) == 2
    assert "usage: python -m app.jobs <name>" in capsys.readouterr().err


def test_missing_job_name_exits_with_usage_error() -> None:
    assert main([]) == 2
