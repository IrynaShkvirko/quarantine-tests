import pytest


def test_stable():
    assert True


def test_fails_then_passes(request):
    # execution_count is set by pytest-rerunfailures (1 on first try)
    assert getattr(request.node, "execution_count", 1) >= 2, "first attempt fails"


def test_fails_twice_then_passes(request):
    assert getattr(request.node, "execution_count", 1) >= 3, "attempt fails"


def test_always_fails():
    assert False, "always fails"


@pytest.mark.parametrize("region", ["eu", "us"])
def test_param_flaky(request, region):
    if region == "eu":
        assert getattr(request.node, "execution_count", 1) >= 2, "eu first attempt fails"


class TestNested:
    def test_in_class(self):
        assert True
