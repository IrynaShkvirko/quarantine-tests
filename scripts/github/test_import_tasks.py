# mypy: allow-untyped-defs
from pathlib import Path
from typing import Any

import import_tasks as it
import pytest
from import_tasks import GhError, Importer, Issue, ProjectState, Task

HEADER = "ID,Milestone,Task,Component,Est. days,Depends on,Status,Doc §,Scope,Acceptance criteria\n"


def csv_of(*rows: str) -> str:
    return HEADER + "\n".join(rows) + "\n"


BASE = csv_of(
    'M0-01,M0,Repo skeleton,infra,1,,Todo,§16,Make repo,"- [ ] works"',
    "M0-02,M0,Spike: ingest,backend,0.5,M0-01,Todo,§3,Try it,- [ ] done",
    "M1-01,M1,Endpoint,backend/ci,2,M0-01 M0-02,Later,§4,Build,- [ ] ok",
)


class FakeGh:
    def __init__(self, native_deps: bool = True) -> None:
        self.ms: dict[str, tuple[int, str]] = {}
        self.lbl: dict[str, tuple[str, str]] = {}
        self.items: list[Issue] = []
        self.blocks: dict[int, set[int]] = {}
        self.native = native_deps
        self.project: ProjectState | None = None
        self.writes: list[str] = []

    def _w(self, what: str) -> None:
        self.writes.append(what)

    def milestones(self):
        return dict(self.ms)

    def upsert_milestone(self, title, description, number):
        self._w("milestone")
        self.ms[title] = (number or len(self.ms) + 1, description)

    def labels(self):
        return dict(self.lbl)

    def upsert_label(self, name, color, description):
        self._w("label")
        self.lbl[name] = (color, description)

    def issues(self):
        return list(self.items)

    def create_issue(self, title, body, labels, milestone):
        self._w("create")
        n = len(self.items) + 1
        self.items.append(Issue(n, title, body, frozenset(labels), milestone))
        return n

    def edit_issue(self, number, title, body, add_labels, remove_labels, milestone):
        self._w(f"edit #{number}")
        i = next(k for k, x in enumerate(self.items) if x.number == number)
        labels = (self.items[i].labels | set(add_labels)) - set(remove_labels)
        self.items[i] = Issue(number, title, body, frozenset(labels), milestone)

    def blocked_by(self, number):
        if not self.native:
            raise GhError("404")
        return sorted(self.blocks.get(number, set()))

    def add_blocked_by(self, number, blocker):
        self._w("block")
        self.blocks.setdefault(number, set()).add(blocker)

    def project_state(self):
        return self.project

    def create_project(self):
        self._w("project")
        self.project = ProjectState(True, True, {})

    def fix_project_fields(self, rewrite_status=False):
        self._w("fields")
        self.project = ProjectState(True, True, self.project.estimates if self.project else {})

    def add_to_board(self, number, estimate):
        self._w("board")
        assert self.project
        self.project.estimates[number] = estimate

    def set_estimate(self, number, estimate):
        self._w("estimate")
        assert self.project
        self.project.estimates[number] = estimate


def run(gh: FakeGh, text: str = BASE, **kw: Any) -> Importer:
    imp = Importer(gh, it.parse_tasks(text), **kw)
    imp.run()
    return imp


def actions(imp: Importer, prefix: str = "") -> list[tuple[str, str]]:
    return [(r.what, r.action) for r in imp.rows if r.what.startswith(prefix)]


# ---- CSV parsing


def test_parse_columns_and_values():
    a, b, c = it.parse_tasks(BASE)
    assert (a.id, a.milestone, a.title, a.estimate, a.depends) == (
        "M0-01",
        "M0",
        "Repo skeleton",
        1.0,
        (),
    )
    assert b.spike and b.depends == ("M0-01",)
    assert c.later and c.components == ("backend", "ci") and c.depends == ("M0-01", "M0-02")
    assert c.labels == {"milestone:M1", "backend", "ci", "later"}


@pytest.mark.parametrize(
    ("text", "msg"),
    [
        (csv_of("X1,M0,t,infra,1,,Todo,,,"), "bad task ID"),
        (csv_of("M0-01,M0,t,nope,1,,Todo,,,"), "unknown component"),
        (csv_of("M0-01,M0,t,infra,abc,,Todo,,,"), "bad estimate"),
        (csv_of("M0-01,M0,t,infra,nan,,Todo,,,"), "bad estimate"),
        (csv_of("M0-01,M0,t,infra,-1,,Todo,,,"), "bad estimate"),
        (csv_of("M0-01,,t,infra,1,,Todo,,,"), "empty milestone"),
        (csv_of("M0-01,M0,t,infra,1,,,,,", "M0-01,M0,u,infra,1,,,,,"), "duplicate"),
        (csv_of("M0-01,M0,t,infra,1,M0-09,,,,"), "unknown task M0-09"),
        ("ID,Task\nM0-01,t\n", "lacks column"),
    ],
)
def test_parse_rejects_bad_rows(text, msg):
    with pytest.raises(ValueError, match=msg):
        it.parse_tasks(text)


# ---- bodies


def _task(**kw: Any) -> Task:
    base = {
        "id": "M0-03",
        "milestone": "M0",
        "title": "t",
        "components": (),
        "estimate": None,
        "depends": ("M0-02",),
        "later": False,
        "spike": False,
        "doc_ref": "",
        "scope": "S",
        "criteria": "C",
    }
    return Task(**{**base, **kw})


def test_body_from_file_strips_header_fills_deps_and_keeps_prose_marker(tmp_path: Path) -> None:
    (tmp_path / "M0-03.md").write_text(
        "title: [M0-03] x\nlabels: a\n---\nDepends {{DEPENDS}}\n"
        "quotes `<!-- fq-task-id: M0-01 -->` here\n"
        "<!-- fq-task-id: M0-03 -->\n"
    )
    body = it.build_body(_task(), tmp_path, {"M0-02": 7})
    assert body == (
        "Depends #7 (M0-02)\nquotes `<!-- fq-task-id: M0-01 -->` here\n\n<!-- fq-task-id: M0-03 -->"
    )


def test_body_from_csv_when_no_file():
    body = it.build_body(_task(depends=()), None, {})
    assert (
        body == "**Scope.** S\n\n**Acceptance criteria**\nC\n\n**Depends on:** none\n\n"
        "<!-- fq-task-id: M0-03 -->"
    )


# ---- marker matching


def _issue(n: int, title: str, body: str) -> Issue:
    return Issue(n, title, body, frozenset(), None)


def test_marker_beats_title_and_prose_marker_is_ignored():
    prose = _issue(
        1, "[M0-03] a", "see `<!-- fq-task-id: M0-01 -->` in text\n<!-- fq-task-id: M0-03 -->"
    )
    other = _issue(2, "[M0-01] b", "no marker")
    by_marker, by_title = it.index_issues([prose, other])
    assert set(by_marker) == {"M0-03"} and by_marker["M0-03"].number == 1
    assert by_title["M0-01"].number == 2


def test_duplicate_marker_is_an_error():
    body = "x\n<!-- fq-task-id: M0-01 -->"
    with pytest.raises(ValueError, match="both carry"):
        it.index_issues([_issue(1, "a", body), _issue(2, "b", body)])


# ---- reconcile end to end


def test_first_run_creates_everything_second_run_changes_nothing():
    gh = FakeGh()
    run(gh)
    assert [i.title for i in gh.items] == [
        "[M0-01] Repo skeleton",
        "[M0-02] Spike: ingest",
        "[M1-01] Endpoint",
    ]
    assert set(gh.ms) == {"M0", "M1"} and len(gh.project.estimates if gh.project else {}) == 3
    gh.writes.clear()
    imp = run(gh)
    assert gh.writes == []
    assert "no changes" in it.format_rows(imp.rows, False)


def test_dependency_links_point_to_right_numbers_and_native_set():
    gh = FakeGh()
    run(gh)
    assert "**Depends on:** #1 (M0-01), #2 (M0-02)" in gh.items[2].body
    assert gh.blocks == {2: {1}, 3: {1, 2}}


def test_native_dependency_failure_keeps_body_list_and_warns():
    gh = FakeGh(native_deps=False)
    imp = run(gh)
    assert imp.warnings and "#1 (M0-01)" in gh.items[1].body


def test_later_task_has_label_and_no_milestone_and_is_on_board():
    gh = FakeGh()
    run(gh)
    later = gh.items[2]
    assert "later" in later.labels and later.milestone is None and gh.project
    assert 3 in gh.project.estimates


def test_title_change_updates_only_that_issue():
    gh = FakeGh()
    run(gh)
    gh.writes.clear()
    imp = run(gh, BASE.replace("Repo skeleton", "Repo skeleton v2"))
    assert gh.writes == ["edit #1"]
    assert [r.detail for r in imp.rows if r.action == "update" and r.what == "M0-01"] == ["title"]


def test_existing_marker_issues_are_adopted_not_created():
    gh = FakeGh()
    run(gh)
    adopted = FakeGh()
    adopted.items = [
        Issue(
            i.number,
            i.title,
            "old body\n" + i.body[i.body.rindex("<!--") :].strip(),
            frozenset(),
            "M0",
        )
        for i in gh.items
    ]
    imp = run(adopted)
    assert not any(a == "create" for w, a in actions(imp, "M0-"))
    assert all(r.how == "marker" for r in imp.rows if r.what.startswith("M0-"))


def test_title_prefix_adopts_issue_without_marker():
    gh = FakeGh()
    gh.items = [_issue(5, "[M0-01] Old name", "old")]
    imp = run(gh)
    row = next(r for r in imp.rows if r.what == "M0-01")
    assert (row.action, row.how, row.ref) == ("update", "title", "#5")
    assert len(gh.items) == 3


def test_dry_run_writes_nothing():
    gh = FakeGh()
    imp = run(gh, dry_run=True)
    assert gh.writes == []
    assert ("M0-01", "create") in actions(imp)
    assert "DRY RUN" in it.format_rows(imp.rows, True)


def test_later_label_removed_when_task_is_scheduled_again():
    gh = FakeGh()
    run(gh)
    run(gh, BASE.replace(",Later,", ",Todo,"))
    assert "later" not in gh.items[2].labels and gh.items[2].milestone == "M1"


def test_issue_scale_13_adopted_63_created_all_on_board() -> None:
    rows = [f"M0-{n:02d},M0,Task {n},infra,1,,Todo,,s,c" for n in range(1, 14)]
    rows += [
        f"M{m}-{n:02d},M{m},Task {m}.{n},backend,1,,Todo,,s,c"
        for m in range(1, 8)
        for n in range(1, 10)
    ]
    text = csv_of(*rows)
    gh = FakeGh()
    gh.items = [
        Issue(
            n, f"[M0-{n:02d}] Task {n}", f"old\n<!-- fq-task-id: M0-{n:02d} -->", frozenset(), "M0"
        )
        for n in range(1, 14)
    ]
    imp = run(gh, text)
    assert len(gh.items) == 76
    assert (
        sum(r.action == "create" and r.what.startswith("M") and "-" in r.what for r in imp.rows)
        == 63
    )
    assert {r.how for r in imp.rows if r.what.startswith("M0-")} == {"marker"}
    assert len({r.what for r in imp.rows if r.what.startswith("milestone")}) == 8
    assert gh.project and len(gh.project.estimates) == 76


def test_title_fallback_skips_issue_with_other_marker_and_rejects_ambiguity() -> None:
    other = _issue(1, "[M0-01] a", "x\n<!-- fq-task-id: M0-07 -->")
    assert it.index_issues([other])[1] == {}
    with pytest.raises(ValueError, match="share the title prefix"):
        it.index_issues([_issue(1, "[M0-01] a", ""), _issue(2, "[M0-01] b", "")])


def test_body_file_problems_are_errors(tmp_path: Path) -> None:
    (tmp_path / "M0-03.md").write_text("title: x\nno separator\n")
    with pytest.raises(ValueError, match="closing"):
        it.build_body(_task(), tmp_path, {})
    (tmp_path / "M0-03.md").unlink()
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("s")
    (tmp_path / "M0-03.md").symlink_to(secret)
    with pytest.raises(ValueError, match="regular files"):
        it.build_body(_task(), tmp_path, {})


def test_body_file_labels_are_allowlisted(tmp_path: Path) -> None:
    (tmp_path / "M0-03.md").write_text("title: x\nlabels: infra, deploy-prod, spike\n---\nbody\n")
    assert it._file_labels(_task(), tmp_path) == {"infra", "spike"}


def test_foreign_status_options_are_kept_and_warned() -> None:
    gh = FakeGh()
    gh.project = ProjectState(True, False, {})
    imp = run(gh)
    assert "fields" not in gh.writes and imp.warnings


def test_body_file_found_in_milestone_subfolder(tmp_path: Path) -> None:
    (tmp_path / "M0").mkdir()
    (tmp_path / "M0" / "M0-03.md").write_text("from file\n")
    assert it.build_body(_task(depends=()), tmp_path, {}).startswith("from file")
