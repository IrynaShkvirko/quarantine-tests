# Agents

Specialized subagents for building the flaky test quarantine system. The design lives in `docs/architecture.md`; tasks live in GitHub Issues; project rules live in `CLAUDE.md`.

Agents declare the skills they load in the `skills:` frontmatter field and the tools they may use in `tools:`. Skills live in `.claude/skills/`.

## Catalog

| Agent | Area | Use it to |
|-------|------|-----------|
| [requirements-planner](requirements-planner.md) | All | Turn a feature or vague issue into a requirements doc checked against `docs/architecture.md` |
| [implementor](implementor.md) | All | Build one GitHub issue; picks skills by area (backend, fq-cli, plugins, CI adapters, Grafana, UI) |
| [test-writer](test-writer.md) | Python, TypeScript plugins | Write deterministic pytest / Vitest tests |
| [backend-reviewer](backend-reviewer.md) | `backend/`, `ci/fq-cli/` | Review FastAPI, domain, SQLAlchemy/Alembic, Procrastinate and integration code |
| [security-reviewer](security-reviewer.md) | All | Review ingestion, webhooks, parsing, credentials, subprocess, workflows |
| [plan-verifier](plan-verifier.md) | All | Check that an issue or plan is fully implemented and its spec covered |
| [refactoring-planner](refactoring-planner.md) | All | Plan a refactoring with characterization tests, safe DB changes and parallel tracks |
| [react-reviewer](react-reviewer.md) | `ui/` (M7) | Review React components and hooks for the custom UI |

## Typical Flow for an Issue

1. **requirements-planner** — only when the issue is new behavior or unclear; output in `docs/requirements/`.
2. `/plan` (writing-plans skill) — for issues bigger than ~1 day; output in `docs/plans/`.
3. **implementor** — builds the issue; runs `make lint typecheck test`.
4. **test-writer** — when tests need to be added or extended separately.
5. **backend-reviewer** and/or **security-reviewer** — on the diff, before you review it.
6. **plan-verifier** — confirms every acceptance criterion is met.
7. `/commit`, `/create-pr` — only when you ask.

## Notes

- Reviewers report findings; they never edit code.
- Planners write documents; they never edit code.
- Every agent treats `docs/architecture.md` as the agreed design and flags conflicts instead of resolving them silently.
