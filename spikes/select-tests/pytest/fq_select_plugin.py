"""M0-11 prototype: select pytest tests by quarantine key (exclude / only).

    pytest -p fq_select_plugin --quarantine-mode exclude
    FQ_QUARANTINE_FILE=quarantine.yaml FQ_QUARANTINE_MODE=only pytest -p fq_select_plugin

The list always comes from a file (option or FQ_QUARANTINE_FILE), never from the command line.
The key of an item is `pytest::<nodeid>` (architecture.md §3.1).
Deselected items go through `pytest_deselected`, so they are not reported as skipped and do not
appear in --junitxml.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

PREFIX = "pytest::"
MODES = frozenset({"off", "exclude", "only"})


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("quarantine")
    group.addoption("--quarantine-file", default=os.environ.get("FQ_QUARANTINE_FILE"))
    group.addoption(
        "--quarantine-mode",
        choices=sorted(MODES),
        default=os.environ.get("FQ_QUARANTINE_MODE", "off"),
    )


def load_keys(path: str | Path) -> frozenset[str]:
    data: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    # `tests:` with no entries is YAML null, so `or []`; entries without a string id are ignored.
    ids = (e.get("id") for e in data.get("tests") or [] if isinstance(e, dict))
    return frozenset(i[len(PREFIX) :] for i in ids if isinstance(i, str) and i.startswith(PREFIX))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    mode = config.getoption("--quarantine-mode")
    if mode not in MODES:  # an env default bypasses argparse `choices`; fail closed
        raise pytest.UsageError(f"FQ_QUARANTINE_MODE must be one of {sorted(MODES)}, got {mode!r}")
    if mode == "off":
        return
    path = config.getoption("--quarantine-file")
    if not path:
        raise pytest.UsageError("--quarantine-mode needs --quarantine-file or FQ_QUARANTINE_FILE")
    keys = load_keys(path)

    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        listed = item.nodeid in keys
        (selected if listed == (mode == "only") else deselected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
