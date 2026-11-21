"""Spike: record every attempt and emit one <testcase> per attempt with fq.attempt."""
import xml.etree.ElementTree as ET

_attempts: list[dict] = []


def _first_line(text: str, limit: int = 1000) -> str:
    # assertion rewriting appends repr'd locals on later lines: keep only the first line
    return (text or "").split("\n", 1)[0][:limit]


def pytest_addoption(parser):
    parser.addoption("--fq-junit", default=None, help="write per-attempt JUnit XML here")


def pytest_runtest_logreport(report):
    # rerunfailures reports each failed attempt with outcome "rerun"
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _attempts.append(
            {
                "nodeid": report.nodeid,
                "outcome": report.outcome,  # passed | failed | rerun | skipped
                "duration": report.duration,
                "message": _first_line(_message(report)),
            }
        )


def _message(report) -> str:
    if hasattr(report, "wasxfail"):  # xfail: the reason, not the expected failure
        return report.wasxfail
    if isinstance(report.longrepr, tuple):  # skip: (path, lineno, "Skipped: reason")
        return report.longrepr[2].removeprefix("Skipped: ")
    return getattr(getattr(report.longrepr, "reprcrash", None), "message", "")


def _split(nodeid: str):
    file, _, name = nodeid.partition("::")
    return file, name


def pytest_sessionfinish(session):
    out = session.config.getoption("--fq-junit")
    # pytest-xdist: workers load this conftest too and would race the controller on the same
    # path with only their own subset. Only the controller (no `workerinput`) writes.
    if not out or hasattr(session.config, "workerinput"):
        return
    counts: dict[str, int] = {}
    suite = ET.Element("testsuite", name="pytest")
    for a in _attempts:
        counts[a["nodeid"]] = n = counts.get(a["nodeid"], 0) + 1
        file, name = _split(a["nodeid"])
        parts = name.split("::")
        classname = ".".join([file[:-3].replace("/", ".")] + parts[:-1])
        tc = ET.SubElement(
            suite, "testcase", classname=classname, name=parts[-1], file=file,
            time=f"{a['duration']:.3f}",
        )
        props = ET.SubElement(tc, "properties")
        ET.SubElement(props, "property", name="fq.test_key", value=f"pytest::{file}::{'::'.join(parts)}")
        ET.SubElement(props, "property", name="fq.attempt", value=str(n))
        if a["outcome"] in ("failed", "rerun"):
            ET.SubElement(tc, "failure", message=a["message"])
        elif a["outcome"] == "skipped":
            ET.SubElement(tc, "skipped", message=a["message"])
    suite.set("tests", str(len(_attempts)))
    ET.indent(suite)
    ET.ElementTree(suite).write(out, encoding="utf-8", xml_declaration=True)
