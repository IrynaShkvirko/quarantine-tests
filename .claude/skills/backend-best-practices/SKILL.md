---
name: backend-best-practices
description: "Python backend conventions and anti-pattern catalog for the flaky test quarantine system: FastAPI routes, pure domain logic, SQLAlchemy 2.0 async with psycopg 3, Alembic migrations and partitions, Procrastinate tasks and cron jobs, GitHub/Jira/Slack integration clients, structlog logging, and fq-cli. Use when writing, reviewing or refactoring code under backend/ or ci/fq-cli/."
---

# Backend Best Practices

Conventions for `backend/` and `ci/fq-cli/`. Stack: Python 3.12, FastAPI, pydantic v2, SQLAlchemy 2.0 (async, psycopg 3), Alembic, Procrastinate, structlog, httpx. Architecture: `docs/architecture.md` §7 (layout), §8 (API and sequences), §10 (schema).

## Severity Levels

- **CRITICAL** — wrong decisions, data loss, duplicate side effects (PRs, tickets, messages), security holes
- **HIGH** — reliability or scaling problems: hangs, N+1, unbounded queries, lost errors
- **MEDIUM** — maintainability: layer violations, unclear names, missing types

---

## Layers (CRITICAL)

```
api/           thin HTTP layer: validate → call → map errors
workers/ jobs/ Procrastinate tasks and cron entrypoints: orchestrate
integrations/  GitHub, Jira, Slack clients behind Protocols
db/            models, repositories, views
domain/        pure decision logic — no I/O
config/        pydantic config models and loaders
```

- **`domain/` is pure.** No DB sessions, no HTTP, no files, no environment, no `datetime.now()`. Inputs in, decisions out. Time comes in as a parameter.
- Dependencies point **inward**: api/workers → db, integrations, domain. `domain` imports nothing from the other layers.
- Decision logic (thresholds, policy, state transitions, plan ordering) lives in `domain/`, never inside a route, task or SQL query.
- Routes are thin: parse the request (pydantic), call one service/repository function, map domain errors to HTTP. No business rules in routes.
- Repositories return domain objects or plain dataclasses, not ORM objects with lazy relationships, when crossing into `domain/`.

## Python Style (MEDIUM)

- Full type hints; `mypy --strict` must pass for `domain/` and `config/`.
- Prefer `@dataclass(frozen=True, slots=True)` or pydantic models over dicts for structured data.
- `enum.StrEnum` for closed sets (outcome, evidence, state, reason) — never bare strings compared in many places.
- Small functions with one job; early returns over nested ifs.
- No mutable default arguments. No module-level state except constants and the app/queue singletons.
- Names follow the architecture's vocabulary: flaky occurrence, execution group, candidate, quarantine record, fingerprint.

## Errors (HIGH)

- Define domain exceptions in `domain/errors.py` (e.g. `InvalidUpload`, `UnknownRepository`, `IllegalTransition`). Map them to HTTP status in **one** place (an exception handler in `api/`).
- Never `except:` or `except Exception: pass`. Catch the specific exception, add context, and either handle it or re-raise.
- Errors returned to clients are short and generic for 5xx; validation errors (4xx) list the fields that failed.
- A failure in a side effect (Slack down) must not roll back a state change that already committed; record it and retry (see Tasks).

## FastAPI (HIGH)

- Request and response bodies are pydantic models with `extra="forbid"`. Never accept `dict` or `Any` from clients.
- Dependencies for: DB session, current repository (from the repo token), settings. No globals inside handlers.
- Every route declares `response_model` and status codes; the OpenAPI schema is part of the contract (`docs/contracts/`).
- Long work is never done in the request: the ingestion route stores the upload, enqueues a job and returns `202`.
- Use `async def` routes with async DB access. Never call blocking libraries (`requests`, sync file parsing of big files, `time.sleep`) inside `async` code; push CPU-heavy parsing to the worker.
- Limit request size (`FQ_INGEST_MAX_UPLOAD_MB`) before reading the body into memory.

## Database (CRITICAL / HIGH)

- **SQLAlchemy 2.0 style only:** `select()`, `insert()`, `update()`; `session.execute(...)`; no legacy `Query` API.
- **No SQL from string formatting.** Use expressions or `text()` with bound parameters. Identifiers (partition names) come from code, never input.
- **One session per request or task**, passed down explicitly. Never create sessions inside domain or integration code.
- **Async + relationships:** no lazy loading (it raises in async). Load what you need with `selectinload` / `joinedload`, or query explicitly.
- **Transactions:** one unit of work = one transaction (`async with session.begin():`). External side effects (GitHub, Jira, Slack) happen **after** commit, from a task that can be retried.
- **Upserts** with `insert(...).on_conflict_do_update/do_nothing` on the natural keys in §10 (`(repository_id, test_key)`, `(repository_id, ci_system, run_id)`, the ingestion idempotency key).
- **Bulk writes** for executions: one multi-row insert per batch, not a loop of single inserts.
- **Bounded queries:** every list query has a limit or a time window; detection queries filter by `test_id` and `executed_at` so they hit the indexes.
- **No N+1:** if you query inside a loop over rows, rewrite as one query.
- **Partitions:** `test_executions` is partitioned by month; always include an `executed_at` range in queries over it.
- **Grafana reads views only** in the `reporting` schema; changing a view's columns is a contract change for dashboards.

## Alembic Migrations (CRITICAL)

- One migration per PR that changes the schema; autogenerate, then **read and fix** it by hand.
- Every migration has a working `downgrade()`.
- Never edit a migration that's merged to `main`; add a new one.
- Renames and drops use expand → migrate → contract across releases.
- Adding an index on a big table: `CREATE INDEX CONCURRENTLY` in its own migration (outside a transaction).
- Data backfills go in separate migrations or scripts, in batches.
- A migration test runs `upgrade head` and `downgrade base` on an empty DB in CI.

## Procrastinate Tasks and Cron Jobs (CRITICAL)

- **Idempotent.** Assume every task runs at least once and possibly twice. Use natural keys and upserts; check state before acting ("is a PR for this test already open?").
- **Small payloads:** pass IDs (`upload_id`, `test_id`), never ORM objects or large blobs.
- **Retries:** configure retry with exponential backoff for transient errors (network, 5xx, rate limits). Don't retry validation errors.
- **Locks / queueing locks** for tasks that must not run concurrently for the same key (e.g. one bot PR per repo per cycle).
- **Ordering:** don't assume webhook or task order. State transitions are validated by the state machine; an out-of-order event is logged and ignored or deferred, never forced.
- Cron jobs (`app/jobs/`) are short entrypoints that call domain + repository code; they're safe to run twice in a row.
- **Shadow mode:** any task with external side effects checks the repo's mode first; in `shadow` it records the decision and stops (§4.12).

## Integrations: GitHub, Jira, Slack (HIGH)

- Each client sits behind a `Protocol` in `integrations/<name>/base.py`, with the real client and a fake for tests.
- Use one shared `httpx.AsyncClient` per integration with **explicit timeouts** (connect and read) and limits.
- Retries with exponential backoff and jitter on 429/5xx; respect `Retry-After` and GitHub's rate-limit headers.
- Log every external call at debug level with method, path, status, duration — never tokens or full payloads.
- Map external errors to our own exception types at the client boundary.
- Credentials come from settings (env / secret manager), never from config files in repos.
- Webhooks: verify the signature on the **raw body** before parsing; then dedupe by delivery ID.

## Configuration (MEDIUM)

- Runtime settings only through `app/settings.py` (`FQ_` env vars). No `os.environ` reads elsewhere.
- Behavior config (`teams.yaml`, policy, quarantine list) is loaded and validated by `app/config/` models; code receives model objects, never raw YAML.
- Defaults live in one place (the config model), matching architecture §5.1 and §17.

## Logging and Metrics (HIGH)

- structlog, JSON in `ci`/`prod`. Log events as a short snake_case name plus fields: `log.info("flaky_occurrence_recorded", test_id=..., evidence="rerun")`.
- Bind `request_id`, `upload_id`, `test_id`, `repo` where they exist.
- Never log tokens, auth headers, webhook secrets or unmasked failure messages.
- Expose Prometheus metrics for ingest latency, parse failures, queue depth, external API errors and masking hits (§14).

## Time

- Store `timestamptz` in UTC. Convert to `Europe/Kyiv` only for display (digest, Slack).
- Inject a `Clock` (or pass `now`) wherever time matters: windows, SLAs, probation, max age.

## fq-cli (HIGH)

- Pure helpers (parse JUnit, compute gate result) separate from I/O (files, git, HTTP).
- `subprocess.run([...], check=True)` with a list of arguments; never `shell=True`.
- Clear exit codes: `0` ok, `1` gate failed, `2` usage/config error; upload errors never change the build result (§9.1).
- Works offline for the gate: reads `quarantine.yaml` from disk; only fetch and upload need the network.

---

## Anti-Pattern Catalog

| Anti-pattern | Severity | Instead |
|--------------|----------|---------|
| Business rule inside a route or SQL query | CRITICAL | Pure function in `domain/`, tested alone |
| Side effect inside the DB transaction | CRITICAL | Commit, then enqueue a retryable task |
| Non-idempotent task (creates a PR every run) | CRITICAL | Check existing state, upsert by natural key |
| f-string SQL | CRITICAL | Bound parameters / expressions |
| Editing a merged migration | CRITICAL | New migration |
| `datetime.now()` in domain code | HIGH | Pass `now` / inject a clock |
| HTTP call without timeout | HIGH | Shared client with timeouts and retries |
| Lazy relationship access in async code | HIGH | `selectinload` or explicit query |
| Loop of single-row inserts | HIGH | Bulk insert |
| `except Exception: pass` | HIGH | Specific exception, context, handle or re-raise |
| `dict` request bodies | MEDIUM | pydantic model with `extra="forbid"` |
| Reading `os.environ` in random modules | MEDIUM | `Settings` |
