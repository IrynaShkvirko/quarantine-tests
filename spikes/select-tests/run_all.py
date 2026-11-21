"""Run the M0-11 matrix and write results/results.json.

For every framework x mode it checks the EXACT set of executed tests against the oracle
(expected.json), counts <skipped> in the JUnit file, and measures wall-clock time.

    .venv/bin/python generate.py && .venv/bin/python run_all.py
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
GEN = HERE / ".generated"
BIN = HERE / "node_modules" / ".bin"
PY = HERE / ".venv" / "bin" / "python"
EXPECTED: dict[str, list[str]] = json.loads((GEN / "expected.json").read_text())
REPEATS = 5

Keys = set[str]


def run(
    cmd: list[str], cwd: Path, env: dict[str, str] | None = None
) -> tuple[float, subprocess.CompletedProcess[str]]:
    full_env = {**os.environ, **(env or {})}
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=cwd, env=full_env, capture_output=True, text=True, check=False)
    return time.perf_counter() - t0, p


def skipped_in_junit(path: Path) -> int:
    return sum(1 for _ in ET.parse(path).getroot().iter("skipped"))


# ------------------------------------------------------------------ result -> key set


def pytest_keys(junit: Path) -> Keys:
    """Rebuild keys from JUnit classname/name (classname is the dotted module + classes)."""
    out: Keys = set()
    for tc in ET.parse(junit).getroot().iter("testcase"):
        out.add(f"{tc.get('classname')}|{tc.get('name')}")
    return out


def pytest_expected(keys: list[str]) -> Keys:
    out: Keys = set()
    for k in keys:
        body = k.removeprefix("pytest::")
        head = body.split("[", 1)[0]
        params = body[len(head) :]
        parts = head.split("::")
        file, classes, func = parts[0], parts[1:-1], parts[-1]
        classname = ".".join([file.removesuffix(".py").replace("/", "."), *classes])
        out.add(f"{classname}|{func}{params}")
    return out


def pw_keys(result_json: Path) -> Keys:
    out: Keys = set()

    def walk(suite: dict, titles: list[str], file: str) -> None:
        for spec in suite.get("specs", []):
            out.add(f"playwright::{file}::{' > '.join([*titles, spec['title']])}")
        for child in suite.get("suites", []):
            walk(child, [*titles, child["title"]], file)

    for top in json.loads(result_json.read_text())["suites"]:
        walk({"specs": top.get("specs", []), "suites": top.get("suites", [])}, [], top["file"])
    return out


def jest_keys(result_json: Path, root: Path) -> tuple[Keys, int]:
    out: Keys = set()
    pending = 0
    for f in json.loads(result_json.read_text())["testResults"]:
        rel = os.path.relpath(f["name"], root)
        for t in f["assertionResults"]:
            if t["status"] in ("pending", "skipped"):
                pending += 1  # reported, but not executed
                continue
            out.add(f"jest::{rel}::{' > '.join([*t['ancestorTitles'], t['title']])}")
    return out, pending


# ----------------------------------------------------------------------- the matrix


def verdict(
    name: str,
    mode: str,
    got: Keys,
    want_all: Keys,
    listed: Keys,
    skipped: int,
    secs: float,
    extra: dict | None = None,
) -> dict:
    want = listed if mode == "only" else want_all - listed
    ok = got == want
    r = {
        "case": name,
        "mode": mode,
        "ran": len(got),
        "expected": len(want),
        "exact": ok,
        "skipped_in_junit": skipped,
        "seconds": round(secs, 3),
        "missing": sorted(want - got)[:5],
        "unexpected": sorted(got - want)[:5],
    }
    r.update(extra or {})
    return r


def all_keys_pytest() -> Keys:
    _, p = run(
        [str(PY), "-m", "pytest", "--collect-only", "-q", "-p", "no:randomly"], GEN / "pytest"
    )
    ids = [ln for ln in p.stdout.splitlines() if "::" in ln]
    return {f"pytest::{i}" for i in ids}


def case_pytest(mode: str, qfile: str = "quarantine.yaml", tag: str = "pytest") -> dict:
    cwd = GEN / "pytest"
    junit = cwd / f"junit-{mode}.xml"
    env = {
        "PYTHONPATH": str(HERE / "pytest"),
        "FQ_QUARANTINE_FILE": f"../{qfile}",
        "FQ_QUARANTINE_MODE": mode,
    }
    secs, p = run(
        [
            str(PY),
            "-m",
            "pytest",
            "-p",
            "fq_select_plugin",
            "-p",
            "no:randomly",
            "-q",
            f"--junitxml={junit}",
        ],
        cwd,
        env,
    )
    allk = pytest_expected(list(all_keys_pytest()))
    listed = pytest_expected(EXPECTED["pytest"])
    return verdict(
        tag,
        mode,
        pytest_keys(junit),
        allk,
        listed,
        skipped_in_junit(junit),
        secs,
        {"exit": p.returncode},
    )


def case_playwright(mode: str, variant: str, qfile: str = "quarantine.yaml") -> dict:
    cwd = GEN / "playwright"
    junit, rj = cwd / "junit.xml", cwd / "result.json"
    env = {
        "FQ_QUARANTINE_FILE": f"../{qfile}",
        "FQ_QUARANTINE_MODE": mode if variant == "grep" else "off",
    }
    cmd = [str(BIN / "playwright"), "test"]
    if variant == "test-list":
        lst = cwd / f"list-{mode}.txt"
        subprocess.run(
            [
                "node",
                "--experimental-strip-types",
                "--no-warnings",
                str(HERE / "playwright/quarantine-select.ts"),
                str(GEN / qfile),
                str(lst),
            ],
            check=True,
            cwd=HERE,
        )
        cmd += ["--test-list" if mode == "only" else "--test-list-invert", str(lst)]
    secs, p = run(cmd, cwd, env)
    listed = set(EXPECTED["playwright"])
    _, lp = run(
        [str(BIN / "playwright"), "test", "--list", "--reporter=json"],
        cwd,
        {"FQ_QUARANTINE_MODE": "off"},
    )
    allk = pw_all_from_list(lp.stdout)
    return verdict(
        f"playwright/{variant}",
        mode,
        pw_keys(rj),
        allk,
        listed,
        skipped_in_junit(junit),
        secs,
        {"exit": p.returncode},
    )


def pw_all_from_list(stdout: str) -> Keys:
    out: Keys = set()

    def walk(suite: dict, titles: list[str], file: str) -> None:
        for spec in suite.get("specs", []):
            out.add(f"playwright::{file}::{' > '.join([*titles, spec['title']])}")
        for child in suite.get("suites", []):
            walk(child, [*titles, child["title"]], file)

    for top in json.loads(stdout)["suites"]:
        walk({"specs": top.get("specs", []), "suites": top.get("suites", [])}, [], top["file"])
    return out


def jest_run(
    mode: str, strategy: str, qfile: str
) -> tuple[float, subprocess.CompletedProcess[str], Path, Path]:
    cwd = GEN / "jest"
    junit, rj = cwd / f"junit-{strategy}-{mode}.xml", cwd / f"result-{strategy}-{mode}.json"
    env = {
        "FQ_QUARANTINE_FILE": f"../{qfile}",
        "FQ_QUARANTINE_MODE": mode,
        "FQ_JEST_STRATEGY": strategy,
        "FQ_JUNIT": junit.name,
    }
    args = ["--json", f"--outputFile={rj}"]
    cmd = (
        ["node", str(HERE / "jest/run-with-name-filter.js"), *args]
        if strategy == "name"
        else [str(BIN / "jest"), *args]
    )
    secs, p = run(cmd, cwd, env)
    return secs, p, junit, rj


def jest_universe() -> Keys:
    cwd = GEN / "jest"
    rj = cwd / "result-all.json"
    run([str(BIN / "jest"), "--json", f"--outputFile={rj}"], cwd, {"FQ_QUARANTINE_MODE": "off"})
    return jest_keys(rj, cwd)[0]


def case_jest(
    mode: str, strategy: str, qfile: str = "quarantine.yaml", allk: Keys | None = None
) -> dict:
    secs, p, junit, rj = jest_run(mode, strategy, qfile)
    got, pending = jest_keys(rj, GEN / "jest")
    return verdict(
        f"jest/{strategy}",
        mode,
        got,
        allk or set(),
        set(EXPECTED["jest"]),
        skipped_in_junit(junit),
        secs,
        {"exit": p.returncode, "pending_in_json": pending},
    )


# ----------------------------------------------------------------- hard-case probes


def probe_playwright_gt() -> dict:
    """Titles containing ' > ' are ambiguous with the §3.1 separator."""
    cwd = GEN / "playwright-gt"
    key = "playwright::e2e/gt.spec.ts::A > B > C"
    qf = GEN / "gt.yaml"
    qf.write_text(f'version: 1\ntests:\n  - id: "{key}"\n')
    res = {}
    for variant in ("grep", "test-list"):
        env = {
            "FQ_QUARANTINE_FILE": str(qf),
            "FQ_QUARANTINE_MODE": "only" if variant == "grep" else "off",
        }
        cmd = [str(BIN / "playwright"), "test"]
        if variant == "test-list":
            lst = cwd / "list.txt"
            subprocess.run(
                [
                    "node",
                    "--experimental-strip-types",
                    "--no-warnings",
                    str(HERE / "playwright/quarantine-select.ts"),
                    str(qf),
                    str(lst),
                ],
                check=True,
                cwd=HERE,
            )
            cmd += ["--test-list", str(lst)]
        _, p = run(cmd, cwd, env)
        tail = (p.stdout + p.stderr).strip().splitlines()[-2:]
        res[variant] = {"exit": p.returncode, "tail": tail}
    return res


def timing(cmd_fn, n: int = REPEATS) -> float:
    xs = [cmd_fn() for _ in range(n)]
    return round(statistics.median(xs), 3)


def overhead() -> dict:
    out: dict[str, dict[str, float]] = {}
    qf = "../quarantine.yaml"
    # pytest
    cwd = GEN / "pytest"
    base_env = {"PYTHONPATH": str(HERE / "pytest")}

    def py(args: list[str], env: dict[str, str]) -> float:
        return run(
            [str(PY), "-m", "pytest", "-p", "no:randomly", "-q", *args], cwd, {**base_env, **env}
        )[0]

    pyp = ["-p", "fq_select_plugin"]
    out["pytest"] = {
        "collect_plain": timing(lambda: py(["--collect-only"], {})),
        "collect_plugin_exclude": timing(
            lambda: py(
                [*pyp, "--collect-only"],
                {"FQ_QUARANTINE_FILE": qf, "FQ_QUARANTINE_MODE": "exclude"},
            )
        ),
        "collect_plugin_only": timing(
            lambda: py(
                [*pyp, "--collect-only"], {"FQ_QUARANTINE_FILE": qf, "FQ_QUARANTINE_MODE": "only"}
            )
        ),
        "run_all": timing(lambda: py([], {})),
        "run_plugin_exclude": timing(
            lambda: py(pyp, {"FQ_QUARANTINE_FILE": qf, "FQ_QUARANTINE_MODE": "exclude"})
        ),
        "run_plugin_only": timing(
            lambda: py(pyp, {"FQ_QUARANTINE_FILE": qf, "FQ_QUARANTINE_MODE": "only"})
        ),
    }
    # playwright
    cwd = GEN / "playwright"

    def pw(args: list[str], env: dict[str, str]) -> float:
        return run([str(BIN / "playwright"), "test", *args], cwd, env)[0]

    def e(mode: str) -> dict[str, str]:
        return {"FQ_QUARANTINE_FILE": qf, "FQ_QUARANTINE_MODE": mode}

    out["playwright"] = {
        "collect_plain": timing(lambda: pw(["--list"], {})),
        "collect_grep_exclude": timing(lambda: pw(["--list"], e("exclude"))),
        "collect_grep_only": timing(lambda: pw(["--list"], e("only"))),
        "collect_testlist_only": timing(
            lambda: pw(["--list", "--test-list", str(cwd / "list-only.txt")], {})
        ),
        "run_all": timing(lambda: pw([], {})),
        "run_grep_exclude": timing(lambda: pw([], e("exclude"))),
        "run_grep_only": timing(lambda: pw([], e("only"))),
        "run_testlist_exclude": timing(
            lambda: pw(["--test-list-invert", str(cwd / "list-exclude.txt")], {})
        ),
        "run_testlist_only": timing(lambda: pw(["--test-list", str(cwd / "list-only.txt")], {})),
    }
    # jest (no collect-only mode: whole run)
    cwd = GEN / "jest"

    def jt(cmd: list[str], env: dict[str, str]) -> float:
        return run(cmd, cwd, {"FQ_JUNIT": "t.xml", **env})[0]

    jb = [str(BIN / "jest")]
    nm = ["node", str(HERE / "jest/run-with-name-filter.js")]

    def je(mode: str, strat: str) -> dict[str, str]:
        return {**e(mode), "FQ_JEST_STRATEGY": strat}

    out["jest"] = {
        "run_all": timing(lambda: jt(jb, {"FQ_QUARANTINE_MODE": "off"})),
        "run_register_exclude": timing(lambda: jt(jb, je("exclude", "register"))),
        "run_register_only": timing(lambda: jt(jb, je("only", "register"))),
        "run_name_exclude": timing(lambda: jt(nm, je("exclude", "name"))),
        "run_name_only": timing(lambda: jt(nm, je("only", "name"))),
    }
    return out


def main() -> int:
    results: dict[str, object] = {"cases": []}
    cases: list[dict] = results["cases"]  # type: ignore[assignment]
    for mode in ("exclude", "only"):
        cases.append(case_pytest(mode))
    for variant in ("grep", "test-list"):
        for mode in ("exclude", "only"):
            cases.append(case_playwright(mode, variant))
    ju = jest_universe()
    for strategy in ("register", "name"):
        for mode in ("exclude", "only"):
            cases.append(case_jest(mode, strategy, allk=ju))
    # 300-key list
    for mode in ("exclude", "only"):
        cases.append(case_pytest(mode, "quarantine-300.yaml", "pytest@300keys"))
        cases.append(
            {
                **case_playwright(mode, "grep", "quarantine-300.yaml"),
                "case": "playwright/grep@300keys",
            }
        )
        cases.append(
            {
                **case_playwright(mode, "test-list", "quarantine-300.yaml"),
                "case": "playwright/test-list@300keys",
            }
        )
        c = case_jest(mode, "register", "quarantine-300.yaml", ju)
        cases.append({**c, "case": "jest/register@300keys"})
        c = case_jest(mode, "name", "quarantine-300.yaml", ju)
        cases.append({**c, "case": "jest/name@300keys"})
    results["playwright_gt"] = probe_playwright_gt()
    results["overhead_seconds_median_of_%d" % REPEATS] = overhead()
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )
    for c in cases:
        flag = "OK " if c["exact"] and c["skipped_in_junit"] == 0 else "!! "
        print(
            f"{flag}{c['case']:28} {c['mode']:8} ran={c['ran']:3} expected={c['expected']:3} skipped={c['skipped_in_junit']} t={c['seconds']}s exit={c.get('exit')}"
            + ("" if c["exact"] else f"  missing={c['missing']} unexpected={c['unexpected']}")
        )
    print(json.dumps(results["playwright_gt"], indent=1))
    print(json.dumps(results["overhead_seconds_median_of_%d" % REPEATS], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
