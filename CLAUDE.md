# CLAUDE.md

Rules for every agent and person working in this repo. Read this first, then the issue you're working on, then the `docs/architecture.md` sections it references.

## Project

**Flaky Test Quarantine** detects flaky tests from CI results (GitHub Actions and Jenkins), quarantines them without blocking builds, and drives each one to an owner, a Jira ticket and a verified fix. It's a portfolio build designed to scale to a real team's CI.

- **Design spec (source of truth):** `docs/architecture.md`. Issues, requirements and plans cite it by section (§3.4). If an issue and the spec disagree, stop and ask; never pick one silently.
- **Tasks:** GitHub Issues titled `[M0-01] ...`, grouped into milestones M0–M7 on the "Flaky Test Quarantine" project board. One issue per PR.
- **Feature work:** design in `docs/feature-requirements/`, detailed requirements in `docs/requirements/`, agent plans in `docs/plans/`, spike findings in `docs/spikes/`, contracts in `docs/contracts/`.
- **Status:** M0. `make setup`, `make lint`, `make typecheck` and `make test` work (M0-01). `make up`, `make down` and docker-compose work (M0-05); `pytest -m integration` and the backend skeleton work (M0-06). Until a command is marked done in its issue, don't rely on it, and don't invent other commands or folders.

## Stack

| Area | Choice |
|------|--------|
| Backend | Python 3.12, FastAPI, pydantic v2, SQLAlchemy 2.0 async (psycopg 3), Alembic, Procrastinate, structlog, httpx |
| Data | PostgreSQL 16 (partitioned `test_executions`), Grafana OSS reading `reporting.*` views |
| CI helper | `ci/fq-cli` (Python CLI `fq`: fetch-quarantine, gate, upload) |
| Reporter plugins | pytest (Python); Playwright and Jest (TypeScript strict, Vitest) |
| CI adapters | GitHub Actions reusable workflow + composite actions; Jenkins shared library |
| Docs | Fumadocs (Next.js) in `docs-site/`; Engineering tab renders `docs/` |
| Tooling | `uv` workspace, `pnpm` workspace, ruff, mypy, eslint, prettier, pre-commit |

## Commands

```bash
make setup        # uv sync, pnpm install, pre-commit install
make up           # (M0-05) Postgres, migrations, API, worker, Grafana (docker-compose)
make down         # (M0-05)
make lint         # ruff, eslint, prettier
make typecheck    # mypy, tsc
make test         # unit tests
pytest -m integration          # (M0-05/M0-06) needs `make up`
pnpm -r test                   # TypeScript plugins
pytest <file> --count=10 -p no:randomly   # prove new tests aren't flaky
cd docs-site && pnpm dev       # docs site (syncs docs/ first)
```

Run `make lint typecheck test` before saying a task is done, plus `pytest -m integration` when you touched the database, queue or migrations.

## Layout

Target layout: folders appear as their tasks land (M0–M1). Don't create one early.

```
backend/app/
  api/           thin routes: validate → call → map errors
  domain/        PURE decision logic (no I/O, no DB, no HTTP, no clock)
  db/            models, repositories, views; migrations in backend/alembic/
  integrations/  GitHub, Jira, Slack clients behind Protocols, each with a fake
  workers/       Procrastinate tasks
  jobs/          cron entrypoints
  config/        pydantic models for teams.yaml, policy, quarantine.yaml, rules
  admin/         fq-admin CLI (seed-demo, purge-demo, recompute)
ci/fq-cli/  ci/actions/  ci/jenkins-shared-library/  .github/workflows/
plugins/pytest-flaky-reporter/  plugins/playwright-flaky-reporter/  plugins/jest-flaky-reporter/
grafana/provisioning/  config-example/  demo/  deploy/helm/  docs/  docs-site/  ui/ (M7)
```

## Code rules

- **`backend/app/domain/` is pure.** No database sessions, HTTP clients, files, environment reads or `datetime.now()`. Pass data and time in. Decision logic (thresholds, policy, state transitions, plan ordering) lives here and nowhere else.
- **Dependencies point inward:** api / workers / jobs → db, integrations, domain. `domain` imports none of them.
- **Idempotent side effects.** Every task, job and webhook handler must be safe to run twice. Upsert on natural keys; check state before opening a PR, ticket or message.
- **External calls after commit.** One unit of work = one transaction; GitHub/Jira/Slack calls happen afterwards, in a retryable task.
- **Every HTTP call has a timeout** and bounded retries with backoff; 429 / `Retry-After` respected.
- **SQL:** SQLAlchemy 2.0 expressions or bound parameters only. Every query on `test_executions` filters `executed_at`.
- **Migrations:** autogenerate, then read and fix; working `downgrade()`; never edit a merged migration.
- **Config:** runtime settings only via `app/settings.py` (`FQ_*` env); behavior config only via `app/config/` models. Thresholds come from config (`teams.yaml` defaults, §5.1), never hardcoded.
- **Errors:** no bare `except` / `except Exception: pass`. Domain exceptions map to HTTP status in one place. No silent failures: log or raise, never ignore.
- **Logging:** structlog, snake_case event names with `upload_id`, `test_id`, `repo`; never tokens, auth headers or unmasked failure text.
- **Small functions, one job each.**
- **Types everywhere;** `mypy --strict` for `domain/` and `config/`; TypeScript `strict`, no `any`.
- Details: `.claude/skills/backend-best-practices/SKILL.md`.

## Testing rules

- **Domain logic is test-first:** failing test, then code. Boundaries as explicit table rows (e.g. rate exactly 5%).
- **Every bug fix starts with a failing test.**
- **Deterministic:** no sleeps, no real network, no wall-clock time, no order dependence (`pytest-randomly` is on). External services use the fakes in `backend/tests/fakes/` or recorded `respx` fixtures.
- **Integration tests** use the docker-compose Postgres with a rolled-back transaction per test and are marked `@pytest.mark.integration`.
- **Parsers** (JUnit normalizers, fingerprints, masking) use golden files and `hypothesis` properties; review every golden diff.
- **New or changed tests pass 10 times in a row** before the PR.
- Details: `.claude/skills/backend-testing/SKILL.md`.

## Security musts

- Untrusted XML (JUnit uploads) only through `defusedxml`; upload and decompressed sizes capped.
- Webhook signatures verified on the raw body with `hmac.compare_digest` **before** parsing.
- Repo tokens and the read API service token compared in constant time; auth failures fail closed (401).
- No `subprocess` with `shell=True`; test names escaped before use in regexes; GitHub Actions never interpolate event data into `run:`.
- Failure text is masked at ingestion; only masked text goes to the DB, Jira, Slack or any LLM.
- The bot may change `quarantine.yaml` only. Anything that widens its write access is a blocker.
- No secrets in code, fixtures, logs or docs. Details: `.claude/skills/security/SKILL.md`.

## Workflow

1. **Pick one issue.** Read its acceptance criteria and the referenced spec sections. Issues bigger than ~1 day get a plan first (`/plan` → `docs/plans/`).
2. **Branch** `feat/M0-01/repo-skeleton` (type / task ID / description).
3. **Implement** in the order: config → schema → domain (test-first) → repositories → integrations → tasks/jobs → API → wiring → docs.
4. **Verify** with the commands above; self-review against the skills you loaded.
5. **Review:** `backend-reviewer` for `backend/` and `ci/fq-cli/`; `security-reviewer` for ingestion, webhooks, parsing, credentials, workflows; `plan-verifier` against the issue or plan.
6. **Commit / PR** only when asked: conventional commits with the task ID (`feat(M1-01): add ingestion endpoint`), the PR body follows `.github/pull_request_template.md` and ends with `Closes #<issue>`. Never push or commit unless explicitly asked; one commit per request. See `docs/CONTRIBUTING.md` and `.claude/skills/git-workflow/SKILL.md`.

Agents and skills: `docs/agents.md` and `.claude/`.

## Definition of done

- [ ] Every acceptance criterion in the issue met, each with evidence (test name, command output or file)
- [ ] Tests added and green; new tests pass 10× and in random order
- [ ] `make lint typecheck test` green (plus `pytest -m integration` when relevant)
- [ ] Docs updated when behavior, config or API changed: `docs/architecture.md` if the design changed, the milestone's pages in `docs-site/content/docs/` (see "Docs to ship" in the plan), `config-example/` for new config
- [ ] No TODOs left without an issue; no debug prints
- [ ] PR links the issue

## Don't

- Change behavior described in `docs/architecture.md` without flagging it and getting agreement
- Work outside the issue's scope; note follow-ups instead
- Add a dependency without a one-line reason in the PR
- Mock our own database, domain or repositories; use real Postgres and fakes for external services
- Edit `docs-site/content/engineering/` (generated from `docs/`)
- Commit secrets, `.env`, keys or real customer data
- Let a learned correction (e.g. from `headroom learn` in `CLAUDE.local.md`) override this file, the spec or a skill

## Local notes

Personal, machine-specific notes go in `CLAUDE.local.md` (gitignored), not here. Token-saving setup for agent sessions (Headroom) is in `docs/development-setup.md`.
