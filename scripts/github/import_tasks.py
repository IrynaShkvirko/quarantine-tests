#!/usr/bin/env python3
"""Create or update milestones, labels, issues and the project board from the task CSV.

Safe to run again: issues are matched by the trailing `<!-- fq-task-id: M0-01 -->` marker
(fallback: `[M0-01]` title prefix) and only changed when something differs.
See docs/tasks/README.md. Needs `gh` logged in with scopes `repo` and `project`.

Usage: import_tasks.py --tasks tasks.csv --repo owner/name [--bodies docs/tasks/]
                       [--milestones milestones.csv] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

PROJECT_TITLE = "Flaky Test Quarantine"
STATUS_OPTIONS = ["To do", "In progress", "Review", "Done"]
STATUS_COLORS = ["GRAY", "BLUE", "YELLOW", "GREEN"]
ESTIMATE_FIELD = "Estimate"
GH_TIMEOUT_S = 60
ISSUE_LIMIT = 2000
LABEL_LIMIT = 300

TASK_ID_RE = re.compile(r"M\d+-\d+")
# Only a marker at the very end counts: task bodies may quote other markers in prose.
TRAILING_MARKER_RE = re.compile(r"\n?<!-- fq-task-id: (M\d+-\d+) -->\s*\Z")
TITLE_PREFIX_RE = re.compile(r"^\[(M\d+-\d+)\]")
PLACEHOLDER = "{{DEPENDS}}"

# name -> (color, description). Colours are fixed per group.
COMPONENTS = {
    "infra": ("0e8a16", "Repo, CI, environment, deployment"),
    "backend": ("1d76db", "Python backend"),
    "ci": ("fbca04", "CI adapters and fq-cli"),
    "plugins": ("c5def5", "pytest / Playwright / Jest reporters"),
    "integrations": ("d4c5f9", "GitHub, Jira, Slack clients"),
    "grafana": ("f9d0c4", "Grafana dashboards and views"),
    "demo": ("bfdadc", "Demo data and scenarios"),
    "docs": ("0075ca", "Documentation and docs site"),
    "ui": ("fef2c0", "Web UI"),
}
SPIKE_LABEL = ("spike", ("e99695", "Timeboxed investigation"))
LATER_LABEL = ("later", ("cfd3d7", "Planned, not scheduled"))
MILESTONE_COLOR = "5319e7"


class GhError(RuntimeError):
    pass


@dataclass(frozen=True)
class Task:
    id: str
    milestone: str
    title: str
    components: tuple[str, ...]
    estimate: float | None
    depends: tuple[str, ...]
    later: bool
    spike: bool
    doc_ref: str
    scope: str
    criteria: str

    @property
    def issue_title(self) -> str:
        return f"[{self.id}] {self.title}"

    @property
    def labels(self) -> set[str]:
        out = {f"milestone:{self.id.split('-')[0]}", *self.components}
        if self.spike:
            out.add(SPIKE_LABEL[0])
        if self.later:
            out.add(LATER_LABEL[0])
        return out


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    labels: frozenset[str]
    milestone: str | None


@dataclass(frozen=True)
class ProjectState:
    has_estimate: bool
    status_ok: bool
    estimates: dict[int, float | None]  # issue number -> estimate, for issues on the board


class Gh(Protocol):
    def milestones(self) -> dict[str, tuple[int, str]]: ...
    def upsert_milestone(self, title: str, description: str, number: int | None) -> None: ...
    def labels(self) -> dict[str, tuple[str, str]]: ...
    def upsert_label(self, name: str, color: str, description: str) -> None: ...
    def issues(self) -> list[Issue]: ...
    def create_issue(
        self, title: str, body: str, labels: list[str], milestone: str | None
    ) -> int: ...
    def edit_issue(
        self,
        number: int,
        title: str,
        body: str,
        add_labels: list[str],
        remove_labels: list[str],
        milestone: str | None,
    ) -> None: ...
    def blocked_by(self, number: int) -> list[int]: ...
    def add_blocked_by(self, number: int, blocker: int) -> None: ...
    def project_state(self) -> ProjectState | None: ...
    def create_project(self) -> None: ...
    def fix_project_fields(self, rewrite_status: bool = False) -> None: ...
    def add_to_board(self, number: int, estimate: float | None) -> None: ...
    def set_estimate(self, number: int, estimate: float) -> None: ...


# ---------------------------------------------------------------- parsing


def _norm_header(name: str) -> str:
    return " ".join(name.lower().split())


def parse_tasks(text: str) -> list[Task]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if reader.fieldnames is None:
        raise ValueError("tasks CSV is empty")
    rename = {name: _norm_header(name) for name in reader.fieldnames}
    missing = {"id", "milestone", "task"} - set(rename.values())
    if missing:
        raise ValueError(f"tasks CSV lacks column(s): {', '.join(sorted(missing))}")

    tasks: list[Task] = []
    for line, raw in enumerate(reader, start=2):
        row = {rename[k]: (v or "").strip() for k, v in raw.items() if k in rename}
        where = f"row {line}"
        task_id = row["id"]
        if not task_id:  # blank spreadsheet rows
            continue
        if not TASK_ID_RE.fullmatch(task_id):
            raise ValueError(f"{where}: bad task ID {task_id!r}")
        if not row["milestone"] or not (row["milestone"] + row["task"]).isprintable():
            raise ValueError(f"{where} ({task_id}): empty milestone or control characters")
        parts = [
            p.strip().lower() for p in re.split(r"[,/;]", row.get("component", "")) if p.strip()
        ]
        unknown = [p for p in parts if p not in COMPONENTS and p != SPIKE_LABEL[0]]
        if unknown:
            raise ValueError(f"{where} ({task_id}): unknown component {unknown[0]!r}")
        est = row.get("est. days", "")
        try:
            estimate = float(est) if est else None
            if estimate is not None and not (math.isfinite(estimate) and estimate >= 0):
                raise ValueError
        except ValueError:
            raise ValueError(f"{where} ({task_id}): bad estimate {est!r}") from None
        depends = tuple(
            d for d in re.split(r"[,;\s]+", row.get("depends on", "")) if TASK_ID_RE.fullmatch(d)
        )
        tasks.append(
            Task(
                id=task_id,
                milestone=row["milestone"],
                title=row["task"],
                components=tuple(p for p in parts if p in COMPONENTS),
                estimate=estimate,
                depends=depends,
                later=row.get("status", "").lower() == "later",
                spike=SPIKE_LABEL[0] in parts or row["task"].lower().startswith("spike"),
                doc_ref=row.get("doc §", ""),
                scope=row.get("scope", ""),
                criteria=row.get("acceptance criteria", ""),
            )
        )

    ids = [t.id for t in tasks]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"duplicate task ID(s): {', '.join(sorted(dup))}")
    for t in tasks:
        bad = [d for d in t.depends if d not in ids]
        if bad:
            raise ValueError(f"{t.id}: depends on unknown task {bad[0]}")
    return tasks


def parse_milestone_descriptions(text: str) -> dict[str, str]:
    """CSV with `Milestone` (or `Title`) and `Description` columns."""
    out: dict[str, str] = {}
    for raw in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        row = {_norm_header(k): (v or "").strip() for k, v in raw.items() if k}
        title = row.get("milestone") or row.get("title") or ""
        if title:
            out[title] = row.get("description", "")
    return out


# ---------------------------------------------------------------- bodies


def deps_text(task: Task, numbers: dict[str, int]) -> str:
    if not task.depends:
        return "none"
    return ", ".join(f"#{numbers.get(d, '?')} ({d})" for d in task.depends)


def _body_path(task: Task, bodies: Path | None) -> Path | None:
    """The task's body file, or None. Symlinks and paths outside `bodies` are refused."""
    if not bodies:
        return None
    # bodies/M0-01.md or bodies/M0/M0-01.md (the layout docs/tasks/ has)
    flat, nested = bodies / f"{task.id}.md", bodies / task.id.split("-")[0] / f"{task.id}.md"
    path = flat if flat.exists() or flat.is_symlink() else nested
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.resolve().is_relative_to(bodies.resolve()):
        raise ValueError(f"{path}: body files must be regular files inside {bodies}")
    return path


def _split_file(path: Path) -> tuple[str, str]:
    """(header, body). A file starting with `title:` has a header ended by a `---` line."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("title:"):
        return "", text
    head, sep, body = text.partition("\n---\n")
    if not sep:
        raise ValueError(f"{path}: header has no closing '---' line")
    return head, body


def build_body(task: Task, bodies: Path | None, numbers: dict[str, int]) -> str:
    deps = deps_text(task, numbers)
    path = _body_path(task, bodies)
    if path:
        body = TRAILING_MARKER_RE.sub("", _split_file(path)[1]).strip()
        if PLACEHOLDER in body:
            body = body.replace(PLACEHOLDER, deps)
        else:
            body += f"\n\n**Depends on:** {deps}"
    else:
        parts = [f"**Scope.** {task.scope}", f"**Acceptance criteria**\n{task.criteria}"]
        if task.doc_ref:
            parts.append(f"**Spec:** {task.doc_ref}")
        parts.append(f"**Depends on:** {deps}")
        body = "\n\n".join(parts)
    return f"{body}\n\n<!-- fq-task-id: {task.id} -->"


def _file_labels(task: Task, bodies: Path | None) -> set[str]:
    path = _body_path(task, bodies)
    if not path:
        return set()
    m = re.search(r"^labels: *(.*)$", _split_file(path)[0], re.MULTILINE)
    found = {x.strip() for x in m.group(1).split(",") if x.strip()} if m else set()
    allowed = {*COMPONENTS, SPIKE_LABEL[0], LATER_LABEL[0]}
    return {x for x in found if x in allowed or re.fullmatch(r"milestone:M[0-9]+", x)}


# ---------------------------------------------------------------- matching


def index_issues(issues: list[Issue]) -> tuple[dict[str, Issue], dict[str, Issue]]:
    """Return (by trailing marker, by title prefix). Two issues claiming one ID is an error."""
    by_marker: dict[str, Issue] = {}
    by_title: dict[str, list[Issue]] = {}
    for issue in issues:
        m = TRAILING_MARKER_RE.search(issue.body.replace("\r\n", "\n"))
        if m:
            if m.group(1) in by_marker:
                raise ValueError(
                    f"issues #{by_marker[m.group(1)].number} and #{issue.number} "
                    f"both carry {m.group(1)}"
                )
            by_marker[m.group(1)] = issue
        t = TITLE_PREFIX_RE.match(issue.title)
        if t and not m:  # an issue with another task's marker is never adopted by title
            by_title.setdefault(t.group(1), []).append(issue)
    ambiguous = sorted(k for k, v in by_title.items() if len(v) > 1 and k not in by_marker)
    if ambiguous:
        raise ValueError(f"several issues share the title prefix [{ambiguous[0]}]; fix by hand")
    return by_marker, {k: v[0] for k, v in by_title.items()}


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


# ---------------------------------------------------------------- reconcile


@dataclass
class Row:
    what: str
    action: str  # create | update | skip
    ref: str = ""
    how: str = ""
    detail: str = ""


@dataclass
class Importer:
    gh: Gh
    tasks: list[Task]
    bodies: Path | None = None
    milestone_desc: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
    rows: list[Row] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def _row(self, *args: str, **kw: str) -> Row:
        row = Row(*args, **kw)
        self.rows.append(row)
        return row

    def run(self) -> list[Row]:
        self._milestones()
        self._labels()
        numbers = self._issues()
        self._board(numbers)
        return self.rows

    def _milestones(self) -> None:
        existing = self.gh.milestones()
        titles = sorted({t.milestone for t in self.tasks} | set(self.milestone_desc))
        for title in titles:
            desc = self.milestone_desc.get(title)
            found = existing.get(title)
            if found is None:
                self._row(f"milestone {title}", "create")
                if not self.dry_run:
                    self.gh.upsert_milestone(title, desc or "", None)
            elif desc is not None and desc != found[1]:
                self._row(f"milestone {title}", "update", detail="description")
                if not self.dry_run:
                    self.gh.upsert_milestone(title, desc, found[0])
            else:
                self._row(f"milestone {title}", "skip")

    def _labels(self) -> None:
        wanted: dict[str, tuple[str, str]] = {}
        for t in self.tasks:
            prefix = t.id.split("-")[0]
            wanted[f"milestone:{prefix}"] = (MILESTONE_COLOR, f"Milestone {prefix}")
        wanted.update({k: v for k, v in COMPONENTS.items()})
        wanted.update([SPIKE_LABEL, LATER_LABEL])
        existing = self.gh.labels()
        for name, (color, desc) in sorted(wanted.items()):
            have = existing.get(name)
            if have is None:
                self._row(f"label {name}", "create")
            elif have != (color, desc):
                self._row(f"label {name}", "update", detail="color/description")
            else:
                self._row(f"label {name}", "skip")
                continue
            if not self.dry_run:
                self.gh.upsert_label(name, color, desc)

    def _issues(self) -> dict[str, int]:
        by_marker, by_title = index_issues(self.gh.issues())
        numbers: dict[str, int] = {}
        found: dict[str, tuple[Issue, str]] = {}
        created: dict[str, str] = {}  # task id -> body it was created with

        for t in self.tasks:  # pass 1: create what is missing
            if t.id in by_marker:
                found[t.id] = (by_marker[t.id], "marker")
            elif t.id in by_title:
                found[t.id] = (by_title[t.id], "title")
            else:
                body = build_body(t, self.bodies, numbers)
                if self.dry_run:
                    self._row(t.id, "create", "#?", "", "new issue")
                else:
                    ms = None if t.later else t.milestone
                    n = self.gh.create_issue(t.issue_title, body, sorted(self._labels_for(t)), ms)
                    numbers[t.id] = n
                    created[t.id] = body
                    self._row(t.id, "create", f"#{n}")
                continue
            numbers[t.id] = found[t.id][0].number

        for t in self.tasks:  # pass 2: final bodies, now that every number is known
            if t.id in created:
                body = build_body(t, self.bodies, numbers)
                if body != created[t.id]:
                    self.gh.edit_issue(
                        numbers[t.id], t.issue_title, body, [], [], None if t.later else t.milestone
                    )
            elif t.id in found:
                self._update(t, *found[t.id], build_body(t, self.bodies, numbers))
        self._native_dependencies(numbers)
        return numbers

    def _labels_for(self, t: Task) -> set[str]:
        return t.labels | _file_labels(t, self.bodies)

    def _update(self, t: Task, issue: Issue, how: str, body: str) -> None:
        want_labels = self._labels_for(t)
        want_ms = None if t.later else t.milestone
        add = sorted(want_labels - issue.labels)
        remove = [LATER_LABEL[0]] if LATER_LABEL[0] in issue.labels and not t.later else []
        changes = []
        if issue.title != t.issue_title:
            changes.append("title")
        if _norm(issue.body) != _norm(body):
            changes.append("body")
        if add or remove:
            changes.append("labels")
        if issue.milestone != want_ms:
            changes.append("milestone")
        ref = f"#{issue.number}"
        if not changes:
            self._row(t.id, "skip", ref, how)
            return
        self._row(t.id, "update", ref, how, ", ".join(changes))
        if not self.dry_run:
            self.gh.edit_issue(issue.number, t.issue_title, body, add, remove, want_ms)

    def _native_dependencies(self, numbers: dict[str, int]) -> None:
        if self.dry_run:
            return
        added = 0
        try:
            for t in self.tasks:
                if not t.depends:
                    continue
                have = set(self.gh.blocked_by(numbers[t.id]))
                for d in t.depends:
                    if numbers[d] not in have:
                        self.gh.add_blocked_by(numbers[t.id], numbers[d])
                        added += 1
        except GhError as err:
            self.warnings.append(f"native 'blocked by' links not set (body list only): {err}")
        if added:
            self._row("dependencies", "update", detail=f"{added} native blocked-by link(s) added")

    def _board(self, numbers: dict[str, int]) -> None:
        state = self.gh.project_state()
        if state is None:
            self._row(f"project '{PROJECT_TITLE}'", "create", detail="Status + Estimate fields")
            if not self.dry_run:
                self.gh.create_project()
                state = self.gh.project_state()
            on_board: dict[int, float | None] = {}
        else:
            if state.has_estimate:
                self._row(f"project '{PROJECT_TITLE}'", "skip")
            else:
                self._row(f"project '{PROJECT_TITLE}'", "update", detail="Estimate field")
                if not self.dry_run:
                    self.gh.fix_project_fields()
            if not state.status_ok:  # rewriting options would clear every item's Status
                self.warnings.append(f"board Status options are not {STATUS_OPTIONS}; left as is")
            on_board = state.estimates

        adds = [t for t in self.tasks if numbers.get(t.id) not in on_board]
        sets = [
            t
            for t in self.tasks
            if t.id in numbers
            and numbers[t.id] in on_board
            and t.estimate is not None
            and on_board[numbers[t.id]] != t.estimate
        ]
        self._row(
            "board",
            "update" if adds or sets else "skip",
            detail=f"add {len(adds)}, estimate {len(sets)}",
        )
        if self.dry_run:
            return
        for t in adds:
            self.gh.add_to_board(numbers[t.id], t.estimate)
        for t in sets:
            assert t.estimate is not None
            self.gh.set_estimate(numbers[t.id], t.estimate)


def format_rows(rows: list[Row], dry_run: bool) -> str:
    changed = [r for r in rows if r.action != "skip"]
    cols = [[r.what, r.action, r.ref, r.how, r.detail] for r in rows]
    widths = [max(len(c[i]) for c in cols) for i in range(4)]
    lines = ["  ".join(c[i].ljust(widths[i]) for i in range(4)) + "  " + c[4] for c in cols]
    summary = (
        "no changes"
        if not changed
        else ", ".join(
            f"{n} {a}" for a in ("create", "update") if (n := sum(r.action == a for r in rows))
        )
    )
    prefix = "DRY RUN (nothing written): " if dry_run else ""
    return "\n".join(lines).rstrip() + f"\n\n{prefix}{summary}"


# ---------------------------------------------------------------- real gh


class RealGh:
    def __init__(self, repo: str) -> None:
        self.repo = repo
        self.owner = repo.split("/")[0]
        self._project: tuple[int, str] | None = None
        self._item_ids: dict[int, str] = {}
        self._fields: dict[str, dict[str, Any]] | None = None

    # shortcut: no retries on gh failures; re-run the script, it is idempotent.
    def _run(self, *args: str, stdin: str | None = None) -> str:
        res = subprocess.run(  # list args, no shell
            ["gh", *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_S,
            check=False,
        )
        if res.returncode:
            raise GhError(f"gh {' '.join(args[:3])}: {res.stderr.strip()}")
        return res.stdout

    @staticmethod
    def _not_truncated(data: list[Any], limit: int, what: str) -> None:
        if len(data) >= limit:  # a cut-off list would make existing items look missing
            raise GhError(f"{what} list hit the limit of {limit}; raise it in import_tasks.py")

    def _json(self, *args: str) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self._run(*args))
        return result

    def _lines(self, *args: str) -> list[str]:
        return [ln for ln in self._run(*args).splitlines() if ln]

    def milestones(self) -> dict[str, tuple[int, str]]:
        out = self._lines(
            "api",
            "--paginate",
            f"repos/{self.repo}/milestones?state=all&per_page=100",
            "--jq",
            ".[] | {number, title, description}",
        )
        items = [json.loads(ln) for ln in out]
        return {m["title"]: (m["number"], m["description"] or "") for m in items}

    def upsert_milestone(self, title: str, description: str, number: int | None) -> None:
        method, path = ("PATCH", f"/{number}") if number else ("POST", "")
        self._run(
            "api",
            "-X",
            method,
            f"repos/{self.repo}/milestones{path}",
            "-f",
            f"title={title}",
            "-f",
            f"description={description}",
        )

    def labels(self) -> dict[str, tuple[str, str]]:
        data = json.loads(
            self._run(
                "label",
                "list",
                "--repo",
                self.repo,
                "--limit",
                str(LABEL_LIMIT),
                "--json",
                "name,color,description",
            )
        )
        self._not_truncated(data, LABEL_LIMIT, "labels")
        return {x["name"]: (x["color"].lower(), x["description"] or "") for x in data}

    def upsert_label(self, name: str, color: str, description: str) -> None:
        self._run(
            "label",
            "create",
            name,
            "--repo",
            self.repo,
            "--color",
            color,
            "--description",
            description,
            "--force",
        )

    def issues(self) -> list[Issue]:
        data = json.loads(
            self._run(
                "issue",
                "list",
                "--repo",
                self.repo,
                "--state",
                "all",
                "--limit",
                str(ISSUE_LIMIT),
                "--json",
                "number,title,body,labels,milestone",
            )
        )
        self._not_truncated(data, ISSUE_LIMIT, "issues")
        return [
            Issue(
                x["number"],
                x["title"],
                x["body"] or "",
                frozenset(label["name"] for label in x["labels"]),
                (x["milestone"] or {}).get("title"),
            )
            for x in data
        ]

    def create_issue(self, title: str, body: str, labels: list[str], milestone: str | None) -> int:
        args = ["issue", "create", "--repo", self.repo, "--title", title, "--body-file", "-"]
        for label in labels:
            args += ["--label", label]
        if milestone:
            args += ["--milestone", milestone]
        url = self._run(*args, stdin=body).strip()
        return int(url.rsplit("/", 1)[1])

    def edit_issue(
        self,
        number: int,
        title: str,
        body: str,
        add_labels: list[str],
        remove_labels: list[str],
        milestone: str | None,
    ) -> None:
        args = [
            "issue",
            "edit",
            str(number),
            "--repo",
            self.repo,
            "--title",
            title,
            "--body-file",
            "-",
        ]
        for label in add_labels:
            args += ["--add-label", label]
        for label in remove_labels:
            args += ["--remove-label", label]
        args += ["--milestone", milestone] if milestone else ["--remove-milestone"]
        self._run(*args, stdin=body)

    def blocked_by(self, number: int) -> list[int]:
        out = self._lines(
            "api",
            f"repos/{self.repo}/issues/{number}/dependencies/blocked_by",
            "--jq",
            ".[].number",
        )
        return [int(x) for x in out]

    def add_blocked_by(self, number: int, blocker: int) -> None:
        issue_id = self._run("api", f"repos/{self.repo}/issues/{blocker}", "--jq", ".id").strip()
        self._run(
            "api",
            "-X",
            "POST",
            f"repos/{self.repo}/issues/{number}/dependencies/blocked_by",
            "-F",
            f"issue_id={issue_id}",
        )

    # -- project board (Projects v2)

    def _find_project(self) -> tuple[int, str] | None:
        if self._project is None:
            data = self._json(
                "project", "list", "--owner", self.owner, "--format", "json", "-L", "100"
            )
            for p in data["projects"]:
                if p["title"] == PROJECT_TITLE:
                    self._project = (p["number"], p["id"])
        return self._project

    def _field_map(self, refresh: bool = False) -> dict[str, dict[str, Any]]:
        if self._fields is None or refresh:
            number = self._require_project()[0]
            data = self._json(
                "project",
                "field-list",
                str(number),
                "--owner",
                self.owner,
                "--format",
                "json",
                "-L",
                "50",
            )
            self._fields = {f["name"]: f for f in data["fields"]}
        return self._fields

    def _require_project(self) -> tuple[int, str]:
        project = self._find_project()
        if project is None:
            raise GhError(f"project '{PROJECT_TITLE}' not found")
        return project

    def project_state(self) -> ProjectState | None:
        project = self._find_project()
        if project is None:
            return None
        fields = self._field_map(refresh=True)
        status = fields.get("Status", {})
        items = self._json(
            "project",
            "item-list",
            str(project[0]),
            "--owner",
            self.owner,
            "--format",
            "json",
            "-L",
            "2000",
        )["items"]
        estimates: dict[int, float | None] = {}
        for item in items:
            content = item.get("content") or {}
            if content.get("type") == "Issue" and content.get("repository") in (None, self.repo):
                estimates[content["number"]] = item.get(ESTIMATE_FIELD.lower())
                self._item_ids[content["number"]] = item["id"]
        return ProjectState(
            has_estimate=ESTIMATE_FIELD in fields,
            status_ok=[o["name"] for o in status.get("options", [])] == STATUS_OPTIONS,
            estimates=estimates,
        )

    def create_project(self) -> None:
        data = self._json(
            "project", "create", "--owner", self.owner, "--title", PROJECT_TITLE, "--format", "json"
        )
        self._project = (data["number"], data["id"])
        self.fix_project_fields(rewrite_status=True)

    def fix_project_fields(self, rewrite_status: bool = False) -> None:
        number = self._require_project()[0]
        fields = self._field_map(refresh=True)
        if ESTIMATE_FIELD not in fields:
            self._run(
                "project",
                "field-create",
                str(number),
                "--owner",
                self.owner,
                "--name",
                ESTIMATE_FIELD,
                "--data-type",
                "NUMBER",
            )
        status = fields.get("Status", {})
        if rewrite_status and [o["name"] for o in status.get("options", [])] != STATUS_OPTIONS:
            options = [
                {"name": n, "color": c, "description": ""}
                for n, c in zip(STATUS_OPTIONS, STATUS_COLORS, strict=True)
            ]
            query = (
                "mutation($id: ID!, $opts: [ProjectV2SingleSelectFieldOptionInput!]) {"
                " updateProjectV2Field(input: {fieldId: $id, singleSelectOptions: $opts}) {"
                " projectV2Field { ... on ProjectV2SingleSelectField { id } } } }"
            )
            payload = json.dumps(
                {"query": query, "variables": {"id": status["id"], "opts": options}}
            )
            self._run("api", "graphql", "--input", "-", stdin=payload)
        self._field_map(refresh=True)

    def _edit_item(self, item_id: str, field_name: str, flag: str, value: str) -> None:
        project_id = self._require_project()[1]
        self._run(
            "project",
            "item-edit",
            "--id",
            item_id,
            "--project-id",
            project_id,
            "--field-id",
            self._field_map()[field_name]["id"],
            flag,
            value,
        )

    def add_to_board(self, number: int, estimate: float | None) -> None:
        project_number = self._require_project()[0]
        item = self._json(
            "project",
            "item-add",
            str(project_number),
            "--owner",
            self.owner,
            "--url",
            f"https://github.com/{self.repo}/issues/{number}",
            "--format",
            "json",
        )
        self._item_ids[number] = item["id"]
        options = self._field_map().get("Status", {}).get("options", [])
        todo = next((o["id"] for o in options if o["name"] == STATUS_OPTIONS[0]), None)
        if todo:
            self._edit_item(item["id"], "Status", "--single-select-option-id", todo)
        if estimate is not None:
            self._edit_item(item["id"], ESTIMATE_FIELD, "--number", str(estimate))

    def set_estimate(self, number: int, estimate: float) -> None:
        self._edit_item(self._item_ids[number], ESTIMATE_FIELD, "--number", str(estimate))


# ---------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--tasks", type=Path, required=True, help="Implementation Plan sheet exported as CSV"
    )
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--bodies", type=Path, help="folder with one Markdown body per task (M0-01.md)")
    ap.add_argument("--milestones", type=Path, help="optional CSV: Milestone, Description")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    args = ap.parse_args(argv)
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+", args.repo
    ) or args.repo.endswith(("/.", "/..")):
        ap.error("--repo must look like owner/name")

    try:
        tasks = parse_tasks(args.tasks.read_text(encoding="utf-8"))
        desc = (
            parse_milestone_descriptions(args.milestones.read_text(encoding="utf-8"))
            if args.milestones
            else {}
        )
        imp = Importer(RealGh(args.repo), tasks, args.bodies, desc, args.dry_run)
        rows = imp.run()
    except (ValueError, OSError, GhError, subprocess.TimeoutExpired) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(format_rows(rows, args.dry_run))
    for w in imp.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
