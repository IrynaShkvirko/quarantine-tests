import pytest

from app.__main__ import main


def test_unknown_command_exits_with_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bogus"]) == 2
    assert "usage: python -m app worker" in capsys.readouterr().err
