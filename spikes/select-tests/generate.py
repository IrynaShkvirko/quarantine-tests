"""Generate the M0-11 fixtures: a 500-test suite per framework and the quarantine lists.

Output (all under .generated/, gitignored):
  pytest/      tests/**.py                       500 tests
  playwright/  e2e/**.spec.ts                    500 tests
  jest/        src/**/*.test.js                  500 tests
  quarantine.yaml       20 keys per framework (60 entries), format of architecture.md §5.3
  quarantine-300.yaml   300 keys per framework (20 real + 280 long keys that match nothing)
  expected.json         expected listed keys per framework (the oracle for run_all.py)

Key format (§3.1): {framework}::{file_path}::{test_name}[{params}]
  pytest      -> pytest nodeid, ids escaped by pytest itself (unicode becomes \\uXXXX)
  playwright  -> describe titles and test title joined with " > "
  jest        -> describe names and test name joined with " > "
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent / ".generated"
TOTAL = 500
LISTED = 20


def ascii_escaped(s: str) -> str:
    """Same escaping pytest applies to parametrize ids."""
    return s.encode("unicode_escape").decode("ascii")


# --------------------------------------------------------------------------- pytest


def gen_pytest() -> list[str]:
    base = ROOT / "pytest"
    tests = base / "tests"
    tests.mkdir(parents=True)
    keys: list[str] = []
    count = 0

    # Hard cases -------------------------------------------------------------
    hard_ids = [
        "a[b]c",  # brackets inside the id
        "with space",
        "café-日本",  # unicode, escaped by pytest in the nodeid
        "x::y",  # :: inside a parameter
        "a::b::c d",
        "1",  # decoy neighbours: 10 and 11 stay in the run
        "q?*+.$^|()",  # regex characters
    ]
    decoy_ids = ["10", "11", "a[b]", "with  space", "x::z", "q"]
    lines = ["import pytest", ""]
    lines.append(f"@pytest.mark.parametrize('p', {hard_ids + decoy_ids!r}, ids=lambda v: v)")
    lines.append("def test_param(p):\n    assert p\n")
    (tests / "test_hard_param.py").write_text("\n".join(lines))
    for pid in hard_ids:
        keys.append(f"pytest::tests/test_hard_param.py::test_param[{ascii_escaped(pid)}]")
    count += len(hard_ids) + len(decoy_ids)

    # same function name in two files, only the first is listed
    for name in ("a", "b"):
        (tests / f"test_dup_{name}.py").write_text("def test_dup():\n    assert True\n")
    keys.append("pytest::tests/test_dup_a.py::test_dup")
    count += 2

    # nested class
    (tests / "test_cls.py").write_text(
        "class TestOuter:\n"
        "    def test_method(self):\n        assert True\n"
        "    class TestInner:\n"
        "        def test_method(self):\n            assert True\n"
    )
    keys.append("pytest::tests/test_cls.py::TestOuter::TestInner::test_method")
    count += 2

    # Plain filler, 5 plain tests are listed so the list has 20 keys in total.
    i = 0
    plain_listed = LISTED - len(keys)
    while count < TOTAL:
        f = tests / f"test_plain_{i // 20:02d}.py"
        with f.open("a") as fh:
            fh.write(f"def test_case_{i:04d}():\n    assert True\n\n")
        if plain_listed and i % 41 == 3:
            keys.append(f"pytest::tests/test_plain_{i // 20:02d}.py::test_case_{i:04d}")
            plain_listed -= 1
        i += 1
        count += 1
    assert len(keys) == LISTED, len(keys)
    (base / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    return keys


# ------------------------------------------------------------------------ playwright

# (file, describe path, title) for the hard cases; "listed" decides membership.
PW_HARD = [
    ("e2e/hard.spec.ts", [], "title ( ) [ ] . * + ? $ ^ |"),
    ("e2e/hard.spec.ts", [], "quotes \"double\" 'single' `tick`"),
    ("e2e/hard.spec.ts", [], "backslash \\\\ and slash / and percent %"),
    ("e2e/hard.spec.ts", ["Outer", "Inner"], "nested describe test"),
    ("e2e/hard.spec.ts", ["Outer"], "nested describe test"),  # decoy: same title, one level up
    ("e2e/hard.spec.ts", [], "unicode café 日本 \U0001f680"),
    ("e2e/hard.spec.ts", ["Group (a|b) [x]"], "regex chars in describe"),
    ("e2e/dup_a.spec.ts", ["Dup"], "same title"),
    ("e2e/dup_b.spec.ts", ["Dup"], "same title"),  # decoy
]
# Listed subset of PW_HARD (by index)
PW_HARD_LISTED = {0, 1, 2, 3, 5, 6, 7}
# Titles that contain " > ": ambiguous with the separator of §3.1 (see findings)
PW_GT = [
    ("e2e/gt.spec.ts", ["A"], "B > C"),
    ("e2e/gt.spec.ts", ["A > B"], "C"),  # same key as the line above
]


def ts_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def gen_playwright() -> list[str]:
    base = ROOT / "playwright"
    e2e = base / "e2e"
    e2e.mkdir(parents=True)
    keys: list[str] = []
    per_file: dict[str, list[tuple[list[str], str]]] = {}
    count = 0

    for idx, (file, desc, title) in enumerate(PW_HARD):
        per_file.setdefault(file, []).append((desc, title))
        if idx in PW_HARD_LISTED:
            keys.append("playwright::{}::{}".format(file, " > ".join([*desc, title])))
        count += 1

    i = 0
    plain_listed = LISTED - len(keys)
    while count < TOTAL:
        file = f"e2e/plain_{i // 20:02d}.spec.ts"
        per_file.setdefault(file, []).append((["Plain suite"], f"case {i:04d}"))
        if plain_listed and i % 37 == 5:
            keys.append(f"playwright::{file}::Plain suite > case {i:04d}")
            plain_listed -= 1
        i += 1
        count += 1

    for file, items in per_file.items():
        out = ["import { test, expect } from '@playwright/test';", ""]
        # group consecutive tests by describe path (simple: one describe tree per test)
        for desc, title in items:
            indent = ""
            for d in desc:
                out.append(f"{indent}test.describe({ts_str(d)}, () => {{")
                indent += "  "
            out.append(f"{indent}test({ts_str(title)}, async () => {{ expect(1).toBe(1); }});")
            for _ in desc:
                indent = indent[:-2]
                out.append(f"{indent}}});")
        (base / file).write_text("\n".join(out) + "\n")
    assert len(keys) == LISTED, len(keys)
    return keys


def gen_playwright_gt() -> None:
    """Separate mini suite: titles containing ' > ' (not part of the 500)."""
    base = ROOT / "playwright-gt"
    (base / "e2e").mkdir(parents=True)
    out = ["import { test, expect } from '@playwright/test';", ""]
    for _, desc, title in PW_GT:
        out.append(f"test.describe({ts_str(desc[0])}, () => {{")
        out.append(f"  test({ts_str(title)}, async () => {{ expect(1).toBe(1); }});")
        out.append("});")
    (base / "e2e/gt.spec.ts").write_text("\n".join(out) + "\n")


# ---------------------------------------------------------------------------- jest

JEST_HARD = [
    ("src/hard.test.js", [], "title ( ) [ ] . * + ? $ ^ |"),
    ("src/hard.test.js", [], "quotes \"double\" 'single' `tick`"),
    ("src/hard.test.js", [], "arrow a > b in title"),
    ("src/hard.test.js", ["Outer", "Inner"], "nested describe test"),
    ("src/hard.test.js", ["Outer"], "nested describe test"),  # decoy
    ("src/hard.test.js", [], "unicode café 日本 \U0001f680"),
    ("src/hard.test.js", ["Group (a|b) [x]"], "regex chars in describe"),
    ("src/dup_a.test.js", ["Dup"], "same title"),
    ("src/dup_b.test.js", ["Dup"], "same title"),  # decoy
]
JEST_HARD_LISTED = {0, 1, 2, 3, 5, 6, 7}


def gen_jest() -> list[str]:
    base = ROOT / "jest"
    (base / "src").mkdir(parents=True)
    keys: list[str] = []
    per_file: dict[str, list[tuple[list[str], str]]] = {}
    count = 0
    for idx, (file, desc, title) in enumerate(JEST_HARD):
        per_file.setdefault(file, []).append((desc, title))
        if idx in JEST_HARD_LISTED:
            keys.append("jest::{}::{}".format(file, " > ".join([*desc, title])))
        count += 1
    i = 0
    plain_listed = LISTED - len(keys)
    while count < TOTAL:
        file = f"src/plain_{i // 20:02d}.test.js"
        per_file.setdefault(file, []).append((["Plain suite"], f"case {i:04d}"))
        if plain_listed and i % 37 == 5:
            keys.append(f"jest::{file}::Plain suite > case {i:04d}")
            plain_listed -= 1
        i += 1
        count += 1
    for file, items in per_file.items():
        out: list[str] = []
        for desc, title in items:
            indent = ""
            for d in desc:
                out.append(f"{indent}describe({ts_str(d)}, () => {{")
                indent += "  "
            out.append(f"{indent}test({ts_str(title)}, () => {{ expect(1).toBe(1); }});")
            for _ in desc:
                indent = indent[:-2]
                out.append(f"{indent}}});")
        (base / file).write_text("\n".join(out) + "\n")
    assert len(keys) == LISTED, len(keys)
    return keys


# ---------------------------------------------------------------------------- main

HERE = Path(__file__).parent

PW_CONFIG = """import {{ defineConfig }} from '@playwright/test';
import {{ selection }} from '{here}/playwright/quarantine-select';

export default defineConfig({{
  testDir: '.',
  testMatch: '**/*.spec.ts',
  workers: 4,
  reporter: [['junit', {{ outputFile: process.env.FQ_JUNIT ?? 'junit.xml' }}], ['json', {{ outputFile: process.env.FQ_JSON ?? 'result.json' }}]],
  ...selection(),
}});
"""

JEST_CONFIG = """const select = require('{here}/jest/quarantine-select');
module.exports = {{
  rootDir: __dirname,
  testMatch: ['**/*.test.js'],
  reporters: ['{here}/jest/empty-suite-reporter.js', ['{here}/node_modules/jest-junit', {{ outputDirectory: '.', outputName: process.env.FQ_JUNIT || 'junit.xml' }}]],
  ...select.jestConfig(),
}};
"""


def write_configs() -> None:
    here = str(HERE)
    (ROOT / "playwright" / "playwright.config.ts").write_text(PW_CONFIG.format(here=here))
    (ROOT / "playwright-gt" / "playwright.config.ts").write_text(PW_CONFIG.format(here=here))
    (ROOT / "jest" / "jest.config.js").write_text(JEST_CONFIG.format(here=here))


def main() -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    expected = {"pytest": gen_pytest(), "playwright": gen_playwright(), "jest": gen_jest()}
    gen_playwright_gt()
    write_configs()

    entries = [
        {"id": k, "jira": "SPIKE-1", "since": "2026-11-20", "reason_suggested": "timing"}
        for ks in expected.values()
        for k in ks
    ]
    (ROOT / "quarantine.yaml").write_text(
        yaml.safe_dump({"version": 1, "tests": entries}, allow_unicode=True, sort_keys=False)
    )

    # 300 keys per framework: the 20 real ones + 280 long keys that match nothing (~700 chars each)
    big = []
    for fw, ks in expected.items():
        pad = [f"{fw}::nope/nope_{n}.x::" + ("long name " * 70) + str(n) for n in range(280)]
        big += [{"id": k, "jira": "SPIKE-1", "since": "2026-11-20"} for k in [*ks, *pad]]
    (ROOT / "quarantine-300.yaml").write_text(
        yaml.safe_dump({"version": 1, "tests": big}, allow_unicode=True, sort_keys=False)
    )
    (ROOT / "expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False))
    print(f"generated {TOTAL} tests x 3 frameworks, {LISTED} listed each -> {ROOT}")


if __name__ == "__main__":
    sys.exit(main())
