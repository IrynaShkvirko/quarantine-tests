---
name: writing-plans
description: "Use when you have an approved design, requirements doc or GitHub issue and need a step-by-step implementation plan for the flaky test quarantine system. Activates after brainstorming or requirements approval, or for any issue bigger than about a day. Breaks work into small, verifiable tasks."
---

# Writing Implementation Plans

Create detailed, step-by-step implementation plans from an approved design, a requirements doc (`docs/requirements/`) or a GitHub issue.

## When This Activates

- After a design is approved (brainstorming) or a requirements doc is agreed
- For a GitHub issue estimated at more than ~1 day
- When the user says "plan this" or "break this into tasks"

Small issues (≤ 1 day) don't need a plan: their Implementation section is the plan.

## Core Principles

1. **Audience:** an AI coding agent or new engineer with no context beyond the repo, `CLAUDE.md` and `docs/architecture.md`. Be explicit.
2. **Task size:** each task takes 2–5 minutes of focused work. If longer, split it.
3. **Verifiable:** every task has a verification step.
4. **Sequential:** each task builds on the previous one. No forward references.
5. **Complete:** exact file paths, function signatures, test names. No ambiguity.
6. **Traceable:** every task names the acceptance criterion or architecture section it serves.

## Plan Structure

Write the plan to `docs/plans/YYYY-MM-DD-<task-id>-<name>.md`:

```markdown
# Implementation Plan: <M1-01 Ingestion endpoint>

## Goal
<1–2 sentences>

**Issue:** #<n> · **Architecture:** §8.1, §8.3 · **Requirements:** docs/requirements/<file> (if any)

## Overview
<how the pieces fit: which layers change, which tables, which tasks/routes>

### Files to create
- `backend/app/api/ingest.py` — route
### Files to modify
- `backend/app/main.py` — register router

---

## Tasks

### Task 1: <short title>

**Serves:** AC 2 / §8.3
**File:** `backend/tests/unit/domain/test_masking.py`

**What to do:**
1. Exact steps
2. Exact code to write, or the signature and the pattern to follow
3. Existing code to mirror

**Verification:**
- [ ] `pytest backend/tests/unit/domain/test_masking.py` fails for the right reason (test-first) / passes
```

## Task Writing Rules

### Be explicit
- Exact file path for every task
- Function signatures with types
- Name the existing pattern to follow (e.g. "same structure as `app/integrations/slack/client.py`")
- Imports that are needed

### Be small
Each task is ONE of:
- Write a failing test (domain logic is always test-first)
- Make that test pass
- Add one model / migration / function / route / task
- Change one section of an existing file

### Be verifiable
Use the project's commands:
- `pytest backend/tests/unit/domain/test_detector.py -k threshold`
- `make test` / `make lint` / `make typecheck`
- `pytest -m integration backend/tests/integration/api/test_ingest.py` (needs `make up`)
- `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
- `curl -s localhost:8000/readyz` returns 200
- `pnpm --filter playwright-flaky-reporter test`
- A Grafana panel shows data after `fq-admin seed-demo`

### Task order (backend)

1. **Config** — pydantic models / settings
2. **Schema** — SQLAlchemy model, Alembic migration
3. **Domain** — failing test, then pure function (repeat per rule)
4. **Repository** — DB functions, integration tests
5. **Integration client** — Protocol, real client, fake
6. **Task / job** — Procrastinate task or cron entrypoint, idempotency test
7. **API** — route, request/response models, error mapping
8. **Wiring** — register router/task, settings, docs, `config-example/`
9. **End-to-end check** — one test or manual run through the whole flow

### Task order (other areas)

- **fq-cli:** pure helper + tests → command → `--help` and exit codes → used in action / Jenkins step
- **Plugins:** golden XML fixture → reporter code → sample-suite test → README
- **CI adapters:** composite action / reusable workflow → Jenkins step → demo repo run on both
- **Dashboards:** SQL view + test → panel JSON → check with seeded data

## Anti-Patterns

- **Vague tasks:** "implement detection" is not a task
- **Giant tasks:** more than 5 steps → split
- **Missing paths:** every task has an exact path
- **No verification:** every task says how to check it
- **Forward references:** task 3 must not need task 5
- **Code before test** for anything in `app/domain/`
- **Untraceable tasks:** a task that serves no acceptance criterion is scope creep

## Example

```markdown
### Task 4: Count rerun evidence as a flaky occurrence

**Serves:** AC 1 / §3.4
**File:** `backend/app/domain/detector.py`

**What to do:**
1. Add `def flaky_occurrences(group: list[Attempt]) -> Evidence | None`
2. Return `Evidence.RERUN` when the group (same test, SHA, environment, one execution) has at least one failed and one passed attempt and no attempt's failure is classified `infra`
3. Return `None` otherwise
4. Make the 4 tests written in Task 3 pass

**Verification:**
- [ ] `pytest backend/tests/unit/domain/test_detector.py -k rerun` — 4 passed
- [ ] `make typecheck` clean
```

## Remember

- Plans are living documents: update them when implementation reveals something new
- A good plan makes implementation almost mechanical
- Unsure about a detail → write it as an open question, don't guess
- If the plan would change behavior described in `docs/architecture.md`, flag it at the top
