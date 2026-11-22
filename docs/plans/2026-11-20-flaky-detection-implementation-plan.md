# Flaky Test Detection (Shadow Mode) — Agent Team Implementation Plan

## Context

M2 turns parsed CI results into flaky-test decisions without acting on them. It covers **1 feature design + 2 requirements documents** (REQ-0.x to REQ-9.x) and GitHub issues **M2-01 to M2-13**:

- `docs/feature-requirements/2026-11-20-flaky-detection-shadow-mode-design.md`
- `docs/requirements/detection-backend-requirements.md`
- `docs/requirements/detection-dashboards-requirements.md`

**Already built:** schema v1 with every §10 table (M0-09), config models (M0-07), ingestion, raw uploads, pytest normalizer, `tests` / `ci_runs` / `test_executions` rows, level resolver, Test inventory dashboard (M1).
**Not built yet:** fingerprints, classification, evidence, rates, policy, state machine, ownership, config sync, reporting views, read API, demo flaky tests, seeder, the two dashboards.

The work is split across **6 implementor agents** in **2 phases** (plus a short contracts step) so agents can run in parallel without touching the same files.

---

## Phase 0: Contracts (lead, before Phase 1, ~1 hour)

One small PR that every Phase 1 agent codes against. Without it, agents 1 and 2 would race on the shape of the domain types.

- `backend/app/domain/types.py` (NEW) — frozen dataclasses and enums only, no logic:
  - `Attempt(outcome, duration_ms, fingerprint, category)`, `ExecutionGroup(test_id, commit_sha, environment, attempts_by_run)`
  - `Evidence` (StrEnum: `rerun`, `cross_run`), `Reason` (9 values), `FailureCategory` (`infra`, `test`, `unknown`)
  - `RateInput(occurrences, groups_14d, groups_last30, method)`, `RateResult(rate, occurrences, groups, threshold_met)`
  - `PolicyInput(is_protected, team_quarantined, team_would_quarantine, team_active_tests, team_cap)`, `ShadowOutcome` (StrEnum)
  - `TestState` (StrEnum with every §11 state), `Transition(from_state, to_state, reason)`
- `docs/contracts/reporting-views.md` (NEW) — the view column table from backend requirements §12.
- Agents may add fields in their own modules but must not change these types without updating this plan.

---

## Phase 1: Foundation (5 agents in parallel)

All 5 agents run at the same time. Each owns its files exclusively (see File Ownership).

---

### Agent 1: Backend — Models, Aggregations, Repositories, Routes

**Covers:** REQ-2.5 (environmental view), REQ-4.4–4.5 (daily stats, flips), REQ-6.1–6.5 (read API), data model changes (backend §1), reporting views (backend §12)

**Files:**
- `backend/alembic/versions/0005_reporting_views.py` (NEW) — `reporting.v_flaky_tests`, `v_flakiness_daily`, `v_shadow_decisions`, `v_environmental_runs` exactly as in `docs/contracts/reporting-views.md`; `GRANT SELECT` to `grafana_ro`
- `backend/app/db/repositories/executions.py` (NEW) — `load_run_groups(run_id) -> list[ExecutionGroup]`, `find_opposite_outcomes(test_id, sha, env, since)`, `count_groups(test_id, now)`
- `backend/app/db/repositories/detection.py` (NEW) — `upsert_signatures`, `mark_run_classified`, `insert_flaky_event` (ON CONFLICT DO NOTHING, returns created?), `get_open_shadow_decision`, `record_shadow_decision`, `set_test_state`
- `backend/app/db/repositories/stats.py` (NEW) — `rate_inputs(test_id, now) -> RateInput`, `team_cap_inputs(team_id, repo_id, now) -> PolicyInput parts`, `upsert_daily_stats(day)`, `update_cost_scores(now)`
- `backend/app/jobs/aggregate_daily.py` (NEW) — nightly entrypoint: `upsert_daily_stats(yesterday)`, `update_cost_scores(now)`; safe to run twice
- `backend/app/api/read.py` (NEW) — 4 routes: `GET /api/v1/tests`, `/tests/{id}/history`, `/stats/flakiness`, `/quarantine`
- `backend/app/api/schemas/read.py` (NEW) — `ReadFilters` (shared, backend §8), request/response models with `extra="forbid"`
- `backend/app/api/service_auth.py` (NEW) — `require_service_token` dependency (`FQ_READ_API_TOKEN`, constant-time compare, 401 on failure)
- Tests: `backend/tests/integration/db/test_migrations_0005.py`, `test_detection_repositories.py`, `backend/tests/integration/jobs/test_aggregate_daily.py`, `backend/tests/integration/api/test_read_api.py`

**Patterns to follow:**
- SQLAlchemy 2.0 `select()` / `insert().on_conflict_*`; one session passed in; no session creation in repositories
- Every query over `test_executions` filters `executed_at` (partition pruning); write the query in a comment above each index
- Routes thin: parse `ReadFilters` → call repository → return response model; errors mapped in `app/api/errors.py` (existing)
- Repositories return `domain.types` dataclasses, never ORM objects, across the domain boundary
- Read `.claude/skills/backend-best-practices/SKILL.md` (Database, Alembic, FastAPI sections)

---

### Agent 2: Detection Domain (pure logic)

**Covers:** REQ-0.1, REQ-2.1–2.4 (fingerprint, infra, reason, mass failure), REQ-3.1–3.5 (evidence), REQ-4.1–4.3 (window, rate, Wilson, cost), REQ-5.1–5.6 (policy, state machine)

**Files (all NEW, under `backend/app/domain/`):**
- `fingerprint.py` — `normalize(message) -> str`, `fingerprint(exception_type, masked_message) -> str` (sha256 hex)
- `classifier.py` — `classify(exception_type, message, rules: ReasonRules) -> tuple[FailureCategory, Reason]`
- `mass_failure.py` — `is_environmental(test_count, failed_count, max_same_fingerprint, cfg) -> bool`
- `evidence.py` — `rerun_evidence(group) -> Evidence | None`, `cross_run_evidence(failed_run, passed_run) -> Evidence | None` (same SHA + env, neither environmental, failure not infra)
- `rates.py` — `choose_window(groups_14d, groups_last30)`, `rate(input) -> RateResult`, `wilson_lower_bound(k, n, z=1.96)`, `cost_score(failed_attempts, median_ms, red_builds)`
- `policy.py` — `decide(input) -> ShadowOutcome` (protected → cap → auto); `allowed = max(team_cap × active, team_cap_min_tests)`
- `state_machine.py` — `transition(state, event) -> TestState` with the §11 table; `IllegalTransition` on anything else
- Tests (test-first): `backend/tests/unit/domain/test_fingerprint.py`, `test_classifier.py`, `test_mass_failure.py`, `test_evidence.py`, `test_rates.py`, `test_policy.py`, `test_state_machine.py`; fixtures `backend/tests/fixtures/traces/*.txt` (20+ real-looking stack traces incl. OOM, browser crash, image pull)

**Key constraints:**
- No imports from `app.db`, `app.api`, `app.integrations`, `app.workers`; no `datetime.now()`
- Boundary cases are explicit table rows: rate exactly 5% (not met), 1 occurrence at 10% (not met), 15/60 vs 15/40 failing, 25 same-fingerprint failures, cap floor (12 active tests allows 1, 100 allows 5)
- `hypothesis` properties: fingerprint stable under changed numbers/UUIDs/timestamps/paths; `wilson_lower_bound ≤ k/n`
- Coverage of `app/domain/` ≥ 90%

---

### Agent 3: Ownership & Config Sync

**Covers:** REQ-1.1–1.6

**Files:**
- `backend/app/domain/codeowners.py` (NEW) — parse CODEOWNERS text; `owners_for(path) -> list[str]` with GitHub semantics (last match wins, `*`, `**`, leading `/`, directory patterns, comments, escaped `#`)
- `backend/app/domain/ownership.py` (NEW) — `resolve(path, repo, job_name, tags, codeowners, teams_cfg, policy) -> Ownership(team_slug, product_area, level, is_protected)`; `unowned` / "Unassigned" / "unclassified" fallbacks
- `backend/app/integrations/github/base.py` (NEW) — `GitHubContents` Protocol: `get_file(repo, path, ref) -> str | None`
- `backend/app/integrations/github/contents.py` (NEW) — httpx implementation (App installation token via existing settings, timeouts, retries); LRU + TTL cache by `(repo, path, ref)`
- `backend/app/db/repositories/teams.py` (NEW) — `sync_teams(cfg)` upsert teams and areas, mark removed teams inactive; `load_teams_config()`
- `backend/app/jobs/config_sync.py` (NEW) — fetch `teams.yaml` from `FQ_CONFIG_REPO`, validate with M0-07 loader, `sync_teams`; keep previous on error; metric `fq_config_sync_failures_total`; after sync log a warning and set `fq_unclassified_tests{repo}` (never reject for unclassified tests)
- `backend/app/api/webhooks_github.py` (NEW) — `POST /api/v1/webhooks/github`: raw-body HMAC check, dedupe on delivery ID, enqueue `config_sync` for pushes to the config repo's default branch; ignore other events with 204
- Tests: `backend/tests/unit/domain/test_codeowners.py` (GitHub doc examples), `test_ownership.py`, `backend/tests/integration/jobs/test_config_sync.py`, `backend/tests/integration/api/test_webhook_github.py`, fake in `backend/tests/fakes/github_contents.py` (NEW)

**Patterns to follow:**
- Webhook per `.claude/skills/security/examples.md` §4 (verify raw body first)
- Pure parser and resolver in `domain/`; fetching only in `integrations/`

---

### Agent 4: Demo Data & Seeder

**Covers:** REQ-8.1–8.6

**Files:**
- `demo/fq-demo-shop-api/tests/flaky/` (NEW) — one test per reason, each with `@pytest.mark.demo_flaky` and the header `# DEMO DATA: intentionally flaky`:
  - `test_timing.py` (fixed short sleep before reading an async result)
  - `test_order_dependency.py` (relies on a row another test creates)
  - `test_concurrency.py` (unlocked counter in two threads)
  - `test_external_dependency.py` (stub server dropping ~15% of requests)
  - `test_test_data_env.py` (unique-name collision from a small random range)
  - `test_nondeterminism.py` (asserts set ordering)
  - `test_ci_infra.py` (emits a runner OOM-style failure)
  - `test_product_bug.py` (real race in `app/cart.py`)
- `demo/fq-demo-shop-api/tests/support/flaky.py` (NEW) — reads `FQ_DEMO_FLAKE_RATE` (default 0.2); seeded RNG per test so a rate of 0 is fully stable
- `demo/fq-demo-shop-api/app/cart.py` (MODIFY) — add the deliberate race used by `test_product_bug.py`
- `backend/app/admin/seed_profiles.py` (NEW) — distributions: repos (2), teams (3 + unowned paths), tests per level, flaky share per reason, protected tests, environmental runs (2+), one team over cap, run attempts, shards
- `backend/app/admin/seed_demo.py` (NEW) — `seed_demo(days=28, runs_per_day=3, batch_id)`: creates demo repositories (`is_demo = true`), tests, runs, shards, run attempts, executions with realistic failure messages from `tests/fixtures/traces/`; **writes raw data only** — the derive step is wired by Agent 6
- `backend/app/admin/cli.py` (MODIFY) — register `fq-admin seed-demo` (options `--days`, `--runs-per-day`, `--batch-id`)
- Tests: `backend/tests/integration/admin/test_seed_demo.py` — volumes per REQ-8.4, idempotent per batch, under 2 minutes

**Key constraints:**
- Every seeded row is reachable from a repository with `is_demo = true` and carries `seed_batch_id` where the table has it
- Same SHA appears in several runs (so cross-run evidence exists) and some runs have attempt 2
- Failure messages contain fake secrets in 2–3 traces to prove masking on the demo path (masked by the M1 ingestion code path the seeder reuses)

---

### Agent 5: Grafana Dashboards

**Covers:** REQ-7.1–7.6, REQ-0.6

**Files:**
- `grafana/provisioning/dashboards/flaky-tests.json` (NEW)
- `grafana/provisioning/dashboards/shadow-mode.json` (NEW)
- `grafana/provisioning/dashboards/test-drilldown.json` (NEW, stub: executions table for `$test_id`; M4-10 completes it)
- `grafana/provisioning/dashboards/test-inventory.json` (MODIFY) — add the "Unclassified tests" panel (REQ-7.7)
- `grafana/tests/test_dashboards.py` (NEW) — lint: every panel query uses `reporting.` views only, applies the `$data` filter and all applicable variables, has a title and a "No data" text; links bar present
- `grafana/tests/fixtures/` (NEW) — minimal rows per view for a smoke query test against Postgres (integration marker)

**Key constraints:**
- Build against the column contract in `docs/contracts/reporting-views.md` (views may not exist until Agent 1 merges; the lint test doesn't need a database)
- Layout, titles, colors and thresholds exactly as `detection-dashboards-requirements.md` §1–§4, §10
- Dashboard time zone Europe/Kyiv; percent with one decimal

---

### Supporting Agents (run alongside, not owning files)

| Agent | When | Why |
|-------|------|-----|
| **test-writer** | During Phase 1, on request from Agents 1 and 3 | Integration tests for repositories, jobs, webhook; keeps implementors on implementation |
| **backend-reviewer** | On each Phase 1 PR and the Phase 2 PR | Layer violations, idempotency, query plans, migrations |
| **security-reviewer** | On Agent 3's PR (webhook, GitHub token), Agent 1's PR (service-token auth), Agent 4's seeder (masking of fake secrets) | Signature check order, constant-time compares, no secrets in fixtures |
| **plan-verifier** | After Phase 2 | Walks the coverage matrix below against the code |
| **requirements-planner** | Only if an open question in the feature design changes scope | Keeps the requirements docs in sync with `architecture.md` |

---

## Phase 2: Integration (1 agent, after all Phase 1 agents complete)

### Agent 6: Wiring & Integration

**Covers:** REQ-0.3–0.4 (worker-only, idempotent pipeline), REQ-5.3 (shadow orchestration), REQ-8.3 (derive step), REQ-9.1–9.2 (metrics, decision logs), end-to-end behavior

**New files:**
- `backend/app/workers/detection.py` — Procrastinate tasks:
  - `classify_run(run_id)` — fingerprint + classify each failure (Agent 2) → `upsert_signatures`, mass-failure flag → enqueue `detect_evidence`
  - `detect_evidence(run_id)` — `load_run_groups` → `rerun_evidence` / `cross_run_evidence` → `insert_flaky_event` → enqueue `evaluate_candidate(test_id)` for each new event
  - `evaluate_candidate(test_id)` — `rate_inputs` → `rate` → state transition → if Candidate: `decide` → `record_shadow_decision` (shadow) → back to Watching; queueing lock per `test_id`
  - `resolve_ownership(run_id)` — CODEOWNERS fetch + `resolve` for new/changed tests (runs before `classify_run`)
- `backend/app/admin/recompute.py` — `fq-admin recompute --repo X [--since]`: re-runs the pipeline over stored runs (used by the seeder and after rule changes)
- `backend/tests/e2e/test_detection_shadow_flow.py` — upload two pytest JUnit files on the same SHA (fail then pass) → one flaky event → rate → shadow `auto_quarantine` record; plus protected and over-cap variants; asserts zero GitHub/Jira/Slack fake calls

**Modifications to existing files:**

| File | Change |
|------|--------|
| `backend/app/workers/parse_upload.py` | After a successful parse, enqueue `resolve_ownership(run_id)` |
| `backend/app/workers/__init__.py` | Register detection tasks |
| `backend/app/jobs/__init__.py` | Schedule `aggregate_daily` (nightly 02:15 Europe/Kyiv) and `config_sync` (every 15 min) |
| `backend/app/main.py` | Include `read` and `webhooks_github` routers |
| `backend/app/settings.py` | `read_api_token`, `github_webhook_secret`, `config_repo`, `codeowners_cache_ttl_s` |
| `backend/app/admin/cli.py` | Register `recompute`; `seed-demo` calls `recompute` for the demo repos at the end (derive step) |
| `backend/app/observability/metrics.py` | `fq_detection_latency_seconds`, `fq_flaky_events_total`, `fq_environmental_runs_total`, `fq_shadow_decisions_total{outcome}`, `fq_config_sync_failures_total` |
| `config-example/teams.yaml` | Demo teams and product areas used by the seeder; `team_cap_min_tests: 1`, `verification_repetitions.unclassified: 25` |
| `config-example/reason_rules.yaml` | `infra:` signatures and reason rules matching the demo flaky tests |
| `config-example/quarantine-policy.yaml` | `mode: shadow`, protected paths used by the demo |
| `.env.example` | New settings with comments |
| `docs/architecture.md` | §2: link this plan (§10 already updated in v2.2) |
| `deploy/` | none in M2 (Helm comes in M6) |

---

## Requirement Coverage Matrix

| REQ | Description | Agent | Phase |
|-----|-------------|-------|-------|
| **REQ-0.1** | Pure domain | 2, 3 | 1 |
| **REQ-0.2** | Thresholds from config | 2 (inputs), 6 (wiring config) | 1, 2 |
| **REQ-0.3–0.4** | Worker-only, idempotent | 1 (upserts), 6 (tasks, locks) | 1, 2 |
| **REQ-0.5–0.6** | UTC storage, Kyiv display, English/en-US | 1, 5 | 1 |
| **REQ-0.7** | Masked text only | 2 (uses masked input), 4 (seeder path) | 1 |
| **REQ-1.1–1.5** | Team, area, level, protected | 3 (logic), 6 (task) | 1, 2 |
| **REQ-1.6** | Config sync | 3 | 1 |
| **REQ-2.1–2.3** | Fingerprint, infra, reason | 2 (logic), 1 (storage), 6 (task) | 1, 2 |
| **REQ-2.4** | Environmental runs | 2 (rule), 1 (flag), 6 (task) | 1, 2 |
| **REQ-2.5** | Weekly environmental ratio | 1 (view), 5 (panel) | 1 |
| **REQ-3.1–3.3** | Rerun / cross-run, same SHA + env | 2 (rules), 1 (lookups), 6 (task) | 1, 2 |
| **REQ-3.4** | One occurrence per group | 1 (unique index), 6 (e2e test) | 1, 2 |
| **REQ-3.5** | Evidence for protected tests | 2 | 1 |
| **REQ-4.1–4.3** | Window, rate, Wilson, cost | 2 (math), 1 (inputs) | 1 |
| **REQ-4.4–4.5** | Daily stats, flips | 1 | 1 |
| **REQ-5.1–5.2** | States, policy order | 2 | 1 |
| **REQ-5.3–5.5** | Shadow records, one open decision | 1 (storage), 6 (orchestration) | 1, 2 |
| **REQ-5.6** | State machine enforced | 2 (machine), 6 (callers) | 1, 2 |
| **REQ-6.1–6.5** | Read API | 1 | 1 |
| **REQ-7.1–7.7** | Dashboards, incl. Unclassified tests panel | 5 (panels), 1 (views) | 1 |
| **REQ-8.1–8.2** | Demo flaky tests | 4 | 1 |
| **REQ-8.3** | Seeder + derive | 4 (raw data), 6 (recompute) | 1, 2 |
| **REQ-8.4–8.6** | Volumes, every panel non-empty, idempotent | 4, verified by 6 | 1, 2 |
| **REQ-9.1–9.2** | Metrics, decision logs | 6 | 2 |

**All requirements are covered.**

---

## File Ownership (No Conflicts)

```
Lead (Phase 0):
  NEW  backend/app/domain/types.py
  NEW  docs/contracts/reporting-views.md

Agent 1 (Backend data + read API):
  NEW  backend/alembic/versions/0005_reporting_views.py
  NEW  backend/app/db/repositories/executions.py
  NEW  backend/app/db/repositories/detection.py
  NEW  backend/app/db/repositories/stats.py
  NEW  backend/app/jobs/aggregate_daily.py
  NEW  backend/app/api/read.py
  NEW  backend/app/api/schemas/read.py
  NEW  backend/app/api/service_auth.py
  NEW  backend/tests/integration/db/test_migrations_0005.py
  NEW  backend/tests/integration/db/test_detection_repositories.py
  NEW  backend/tests/integration/jobs/test_aggregate_daily.py
  NEW  backend/tests/integration/api/test_read_api.py

Agent 2 (Detection domain):
  NEW  backend/app/domain/{fingerprint,classifier,mass_failure,evidence,rates,policy,state_machine}.py
  NEW  backend/tests/unit/domain/test_{fingerprint,classifier,mass_failure,evidence,rates,policy,state_machine}.py
  NEW  backend/tests/fixtures/traces/*.txt

Agent 3 (Ownership & config sync):
  NEW  backend/app/domain/codeowners.py
  NEW  backend/app/domain/ownership.py
  NEW  backend/app/integrations/github/base.py
  NEW  backend/app/integrations/github/contents.py
  NEW  backend/app/db/repositories/teams.py
  NEW  backend/app/jobs/config_sync.py
  NEW  backend/app/api/webhooks_github.py
  NEW  backend/tests/fakes/github_contents.py
  NEW  backend/tests/unit/domain/test_codeowners.py
  NEW  backend/tests/unit/domain/test_ownership.py
  NEW  backend/tests/integration/jobs/test_config_sync.py
  NEW  backend/tests/integration/api/test_webhook_github.py

Agent 4 (Demo data & seeder):
  NEW  demo/fq-demo-shop-api/tests/flaky/*.py
  NEW  demo/fq-demo-shop-api/tests/support/flaky.py
  MOD  demo/fq-demo-shop-api/app/cart.py
  NEW  backend/app/admin/seed_profiles.py
  NEW  backend/app/admin/seed_demo.py
  MOD  backend/app/admin/cli.py            (seed-demo command only)
  NEW  backend/tests/integration/admin/test_seed_demo.py

Agent 5 (Grafana):
  NEW  grafana/provisioning/dashboards/flaky-tests.json
  NEW  grafana/provisioning/dashboards/shadow-mode.json
  NEW  grafana/provisioning/dashboards/test-drilldown.json
  MOD  grafana/provisioning/dashboards/test-inventory.json
  NEW  grafana/tests/test_dashboards.py
  NEW  grafana/tests/fixtures/*

Agent 6 (Integration — Phase 2):
  NEW  backend/app/workers/detection.py
  NEW  backend/app/admin/recompute.py
  NEW  backend/tests/e2e/test_detection_shadow_flow.py
  MOD  backend/app/workers/parse_upload.py
  MOD  backend/app/workers/__init__.py
  MOD  backend/app/jobs/__init__.py
  MOD  backend/app/main.py
  MOD  backend/app/settings.py
  MOD  backend/app/admin/cli.py            (recompute + derive step; after Agent 4 merged)
  MOD  backend/app/observability/metrics.py
  MOD  config-example/{teams,reason_rules,quarantine-policy}.yaml
  MOD  .env.example
  MOD  docs/architecture.md
```

`backend/app/admin/cli.py` is the only file touched by two agents; Agent 6 starts only after Agent 4's PR is merged.

---

## Verification

After Phase 2, verify end-to-end (`make up` running):

1. **Migrations:** `alembic upgrade head` → `downgrade -2` → `upgrade head` succeeds; `grafana_ro` can select the 4 views
2. **Quality gates:** `make lint typecheck test`, `pytest -m integration`, `pytest backend/tests/e2e`; new tests pass with `--count=10` and in random order; domain coverage ≥ 90%
3. **Seed:** `fq-admin seed-demo --days 28 --runs-per-day 3` finishes in < 2 min; counts meet REQ-8.4 (≥ 300 tests, ≥ 20 flaky across all reasons, ≥ 5 protected, ≥ 3 unowned, ≥ 2 environmental runs, 1 team over cap); running it again changes nothing
4. **Classification:** the `ci_infra` demo failures have `category = 'infra'` and no flaky events; environmental runs have no flaky events
5. **Evidence:** a demo test run twice on the same SHA (fail, then pass via "Re-run failed jobs") produces exactly one `cross_run` event; reprocessing the upload doesn't add another
6. **Shadow decisions:** `v_shadow_decisions` has all three outcomes; protected-flaky tests show `protected_alert`; the over-cap team shows `needs_lead_approval`; GitHub/Jira/Slack fakes received no calls
7. **Read API:** the 4 endpoints return data with the service token, 401 without it, 400 for a bad `group_by`, 404 for an unknown test; `/stats/flakiness` numbers equal the view
8. **Config sync:** pushing a change to `teams.yaml` in the config repo (or calling the webhook with a signed fixture) updates teams; an invalid file keeps the previous config and increments the failure metric
9. **Dashboards:** open Flaky tests and Shadow mode with `data = demo` — banner visible, every panel shows data for each team and level; test links open the drill-down; with `data = real` and no real data, panels show the no-data text
10. **Live demo run:** run `fq-demo-shop-api` CI twice with `FQ_DEMO_FLAKE_RATE=0.5`; within a minute of the second upload a new shadow decision appears on the Shadow mode dashboard
11. **Docs:** schema matches `docs/architecture.md` v2.2 §10 (`flips`, `shadow_outcome`, `v_environmental_runs`, detection indexes)
12. **plan-verifier** report: every row of the coverage matrix DONE
