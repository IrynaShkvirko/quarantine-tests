# Flaky Test Detection — Backend Requirements

## Feature: Detection Backend (Classification, Evidence, Rates, Shadow Decisions, Read API)

**Summary:** Backend for M2: ownership and level resolution, failure fingerprinting and classification, flaky evidence, flakiness rate and cost, the policy engine and state machine in shadow mode, daily statistics, reporting views and an internal read API.

**Scope:** Backend (Python 3.12, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16, Procrastinate). Grafana dashboards are in `detection-dashboards-requirements.md`.

**References:**
- Feature design: `docs/feature-requirements/2026-11-20-flaky-detection-shadow-mode-design.md` (REQ-0.x to REQ-9.x)
- Architecture: `docs/architecture.md` §3 (concepts), §4.1–4.2, §4.11–4.12 (rules), §5 (config), §8.3–8.4 (sequences), §10 (schema), §11 (states)
- Built in M1: ingestion API, raw uploads, pytest normalizer, `tests` / `ci_runs` / `test_executions` rows, level resolver
- Built in M0: schema v1 (all §10 tables), config models and loaders

---

## Requirement ID Reference

| ID | Description |
|----|-------------|
| REQ-1.1–1.3 | Team from CODEOWNERS, unowned fallback, product area |
| REQ-1.4 | Level from path / job rules, "unclassified" fallback |
| REQ-1.5 | Protected flag from policy file and markers |
| REQ-1.6 | Config sync from the config repo |
| REQ-2.1 | Failure fingerprint |
| REQ-2.2 | Infra classification |
| REQ-2.3 | Suggested reason |
| REQ-2.4–2.5 | Environmental runs and weekly ratio |
| REQ-3.1–3.5 | Rerun and cross-run evidence, one occurrence per group |
| REQ-4.1–4.5 | Window, rate, threshold, cost, daily stats, flips |
| REQ-5.1–5.6 | Candidate states, policy order, shadow decision records |
| REQ-6.1–6.5 | Read API |
| REQ-9.1–9.2 | Metrics and decision logs |

---

## Dependency Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  M1: Upload parsed → tests, ci_runs, test_executions stored      │
└───────────────────────────────┬──────────────────────────────────┘
                                ▼
┌───────────────────────────┐   ┌──────────────────────────────────┐
│ Ownership & Config (REQ-1)│   │ Failure Classification (REQ-2)   │
│ CODEOWNERS, teams.yaml,   │   │ fingerprint, infra, reason,      │
│ area, level, protected    │   │ environmental run                │
└─────────────┬─────────────┘   └───────────────┬──────────────────┘
              └──────────────┬──────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Flaky Evidence (REQ-3): rerun / cross_run → flaky_events        │
└───────────────────────────────┬──────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  Rate & Cost (REQ-4): window, threshold, cost, daily stats       │
└───────────────────────────────┬──────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  Policy & State (REQ-5): candidate → shadow decision record      │
└───────────────────────────────┬──────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  Reporting views + Read API (REQ-6) → Grafana / future UI        │
└──────────────────────────────────────────────────────────────────┘
```

- **REQ-1** and **REQ-2** can be built in parallel; both feed evidence.
- **REQ-3** needs fingerprints and the infra / environmental flags from REQ-2.
- **REQ-4** needs flaky events from REQ-3.
- **REQ-5** needs rates from REQ-4 and team / protected data from REQ-1.
- **REQ-6** reads everything above through `reporting.*` views.

---

## 1. Data Model Changes

Schema v1 (§10, M0-09) already has every table this feature writes. Two columns and one view set are added.

| Change | Table / object | Why | Architecture |
|--------|----------------|-----|--------------|
| ADD `flips int NOT NULL DEFAULT 0` | `daily_test_stats` | REQ-4.5 flip trend | Added in architecture v2.2 (§10) |
| ADD `shadow_outcome text NULL` with CHECK in (`auto_quarantine`, `needs_lead_approval`, `protected_alert`) | `quarantine_records` | REQ-5.3 what enforce mode would do | Added in architecture v2.2 (§10) |
| ADD index `ci_runs (repository_id, commit_sha, environment)` | `ci_runs` | REQ-3.2 cross-run lookup | Implied by §10 indexes |
| CREATE views | `reporting.v_flaky_tests`, `v_flakiness_daily`, `v_shadow_decisions`, `v_environmental_runs` | Dashboards and read API | §10 Grafana contract (`v_environmental_runs` added in v2.2) |

**Acceptance — Data Model:**
- [ ] Migration `0004_detection` adds the two columns and the index, with a working downgrade
- [ ] Migration `0005_reporting_views` creates the four views; `grafana_ro` can `SELECT` them

---

## 2. Ownership and Config Sync (REQ-1)

### 2.1 Resolution rules

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| REQ-1.1 | Team from CODEOWNERS at the run's SHA, last match wins, mapped via `github_team` | Table tests reproduce GitHub's documented CODEOWNERS examples |
| REQ-1.2 | No match → `unowned` | Unknown GitHub team or no pattern → `unowned` team id |
| REQ-1.3 | Product area from team `paths` globs for the repo | No match → `product_area_id = NULL` (shown as "Unassigned") |
| REQ-1.4 | Level from path rules, then job rules | No match → `level = 'unclassified'`; never a config validation error |
| REQ-1.5 | Protected from policy file or markers | `tests.is_protected` true when path glob, test ID or marker matches |

**Input:** test key, file path, repo, commit SHA, CI job name, JUnit tags.
**Output:** `team_id`, `product_area_id`, `level`, `is_protected` written on the `tests` row (updated when they change).

- CODEOWNERS is fetched from GitHub at the commit SHA and cached by `(repo, sha)`; a missing file means every test is `unowned`.
- Resolution is a pure function (`domain/ownership.py`); fetching is an integration (`integrations/github/contents.py`).

### 2.2 Config sync webhook

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/webhooks/github` | HMAC `X-Hub-Signature-256` | On `push` to the config repo's default branch, enqueue `config_sync` |

**Request:**
- Headers: `X-Hub-Signature-256`, `X-GitHub-Event: push`, `X-GitHub-Delivery`
- Body: GitHub push payload (only `repository.full_name` and `ref` are used)

**Response:**
- 204: accepted (sync enqueued, or event ignored because it isn't a push to the config repo's default branch)
- 401: bad signature (payload not parsed, not logged)

**Acceptance — Config Sync:**
- [ ] Signature verified on the raw body with `hmac.compare_digest` before parsing
- [ ] Duplicate `X-GitHub-Delivery` enqueues nothing new
- [ ] `config_sync` cron also runs every 15 minutes
- [ ] Valid `teams.yaml` → `teams` and `product_areas` upserted; removed teams marked inactive, not deleted
- [ ] Invalid `teams.yaml` → previous config kept, error logged, `fq_config_sync_failures_total` incremented
- [ ] After each sync, a warning is logged with the number of unclassified tests per repo, and `fq_unclassified_tests{repo}` is updated

---

## 3. Failure Classification (REQ-2)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| REQ-2.1 | Fingerprint = hash(exception type + normalized masked message) | Property test: messages differing only in numbers, UUIDs, timestamps, temp paths, hex addresses → same fingerprint |
| REQ-2.2 | Infra signatures → `category = 'infra'` | Each signature in `reason_rules.yaml` (`infra:` section) has a positive and a negative test |
| REQ-2.3 | Suggested reason, first matching rule wins, else `untriaged` | Table test per reason in §4.2 |
| REQ-2.4 | Environmental run: > 20% failed with ≥ 50 tests, or one fingerprint failing ≥ 25 tests | 15 of 60 failing → flagged; 15 of 40 failing → not flagged; 25 tests with one fingerprint → flagged |
| REQ-2.5 | Weekly environmental ratio per repo | `reporting.v_environmental_runs` returns runs, environmental runs and ratio per repo per ISO week |

**Input:** the run's executions with masked messages.
**Output:** `failure_signatures` upserted by fingerprint; `test_executions.failure_signature_id` set; `ci_runs.is_environmental`, `test_count`, `failed_count` set.

**Acceptance — Classification:**
- [ ] Re-classifying a run produces the same fingerprints and flags
- [ ] Thresholds come from `defaults.mass_failure` in `teams.yaml`

---

## 4. Flaky Evidence (REQ-3)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| REQ-3.1 | `rerun`: failed then passed attempts within one execution, any branch | Execution with attempts [failed, passed] → one `rerun` event |
| REQ-3.2 | `cross_run`: failed in one run / run attempt, passed in another, same SHA + environment, any branch | Run attempt 1 failed, run attempt 2 passed → one `cross_run` event |
| REQ-3.3 | Never pair different SHAs or environments | Failed on SHA A, passed on SHA B → no event; failed on chromium, passed on firefox → no event |
| REQ-3.4 | At most one occurrence per `(test, sha, environment)` | Re-processing either run doesn't create a second event (unique index + upsert) |
| REQ-3.5 | Protected tests still get evidence | Event recorded with no special case |

Excluded from evidence: failures with `category = 'infra'` and any execution from a run with `is_environmental = true`.

**Output:** `flaky_events` row (`test_id, commit_sha, environment, evidence, branch, failure_signature_id, detected_at`), then `evaluate_candidate(test_id)` enqueued.

**Acceptance — Evidence:**
- [ ] Unique index on `flaky_events (test_id, commit_sha, environment)`
- [ ] Scenario table in `tests/unit/domain/test_evidence.py` covers every row above
- [ ] Integration test: two uploads of the same SHA in either order produce one event

---

## 5. Rate, Cost and Daily Stats (REQ-4)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| REQ-4.1 | Window = whichever has more execution groups: last 14 days or last 30 groups | Test with 10 groups in 14 days → uses last 30 groups; 50 groups in 14 days → uses 14 days |
| REQ-4.2 | Threshold: rate > `flakiness_threshold` and occurrences ≥ `min_flaky_occurrences`; optional Wilson | (1 of 10) → not met; (2 of 40) → not met (exactly 5%); (2 of 39) → met; Wilson matches reference values |
| REQ-4.3 | Cost = failed attempts × median duration + red builds caused × 600 s | Unit test with known inputs |
| REQ-4.4 | Nightly `aggregate_daily` writes `daily_test_stats` | Running twice for the same day leaves identical rows |
| REQ-4.5 | Flips per day, default branch only (nightly included) | Sequence P,F,P,P,F on `main` → 3 flips; the same sequence on a PR branch → 0 |

**Acceptance — Rates:**
- [ ] Rate and occurrences computed in one query per test (no N+1)
- [ ] `tests.cost_score` updated nightly and after each evaluation

---

## 6. Policy and State in Shadow Mode (REQ-5)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| REQ-5.1 | Healthy / Watching / Candidate by threshold | State table tests for every combination |
| REQ-5.2 | Order: protected → cap → auto | Protected and over cap → `protected_alert` (protection wins) |
| REQ-5.3 | Shadow: record `decision='shadow'` + `shadow_outcome`, return to Watching, no external calls | Test asserts fakes for GitHub/Jira/Slack received zero calls |
| REQ-5.4 | Record keeps rate, occurrences, window, reason, fingerprint, evidence run URLs | Fields present and match inputs |
| REQ-5.5 | One open shadow decision per test; new one only on outcome change or after the window | Evaluating twice → one record |
| REQ-5.6 | Transitions through the state machine | Illegal transition raises `IllegalTransition`, logged, state unchanged |

**Team cap (shadow):** over cap when `quarantined + open shadow auto_quarantine ≥ allowed`, with `allowed = max(team_cap × active tests, team_cap_min_tests)` for the team in the repo; active = seen in the last `inventory_stale_days` (architecture D9, D38).

**Acceptance — Policy:**
- [ ] `domain/policy.py` and `domain/state_machine.py` have no imports from `db`, `api`, `integrations`, `workers`
- [ ] Cap floor: team with 12 active tests and nothing quarantined → first candidate `auto_quarantine`, second `needs_lead_approval`; team with 100 active tests allows 5
- [ ] Every transition in §11 reachable in M2 (Healthy, Watching, Candidate, NeedsDecision via shadow, ProtectedFlaky via shadow) has a test

---

## 7. Read API (REQ-6)

All read endpoints are internal (not on the public ingress) and require `Authorization: Bearer <service token>` (`FQ_READ_API_TOKEN`) until OAuth arrives with the UI.

### 7.1 List tests (REQ-6.1)

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/v1/tests` | Service token |

**Request (query):** filters from §8, plus `state`, `protected` (bool), `q` (substring of test key), `sort` (`cost` \| `rate` \| `last_seen`, default `cost`), `limit` (1–200, default 50), `cursor`.

**Response:**
```json
{
  "items": [
    {
      "id": 812,
      "repo": "acme/fq-demo-shop-api",
      "test_key": "pytest::tests/api/test_orders.py::test_create_order[eu]",
      "framework": "pytest",
      "level": "api",
      "team": "payments",
      "product_area": "checkout",
      "state": "watching",
      "is_protected": false,
      "flakiness_rate": 0.071,
      "flaky_occurrences": 3,
      "execution_groups": 42,
      "cost_score": 1840.5,
      "last_seen_at": "2026-11-20T03:12:44Z"
    }
  ],
  "next_cursor": "eyJpZCI6ODEyfQ"
}
```

**Acceptance:**
- [ ] Filters combine with AND; unknown filter values return an empty list, not an error
- [ ] Cursor pagination is stable while new rows arrive

### 7.2 Test history (REQ-6.2)

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/v1/tests/{id}/history` | Service token |

**Request:** `from`, `to` (default last 14 days), `limit` executions (default 200).

**Response:**
```json
{
  "test": { "id": 812, "test_key": "...", "team": "payments", "level": "api", "state": "watching" },
  "executions": [
    { "run_id": "11893422", "run_attempt": 2, "attempt": 1, "commit_sha": "9f2c1e7", "branch": "main",
      "environment": "ubuntu-22.04/py3.12", "outcome": "passed", "duration_ms": 1830,
      "fingerprint": null, "executed_at": "2026-11-19T21:04:10Z", "run_url": "https://github.com/..." }
  ],
  "flaky_events": [
    { "commit_sha": "9f2c1e7", "environment": "ubuntu-22.04/py3.12", "evidence": "cross_run", "detected_at": "..." }
  ],
  "decisions": [
    { "decision": "shadow", "shadow_outcome": "auto_quarantine", "rate_at_entry": 0.071, "occurrences_at_entry": 3,
      "reason_suggested": "timing", "entered_at": "..." }
  ]
}
```

**Acceptance:**
- [ ] 404 for an unknown test id
- [ ] Executions sorted newest first; grouped fields allow showing "run X, attempt 2"

### 7.3 Flakiness statistics (REQ-6.3)

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/v1/stats/flakiness` | Service token |

**Request:** `group_by` (required: `team` \| `product_area` \| `level` \| `reason` \| `environment`), filters from §8.

**Response:**
```json
{
  "group_by": "team",
  "window": { "from": "2026-11-06", "to": "2026-11-20" },
  "rows": [
    { "key": "payments", "tests": 214, "flaky_tests": 9, "flaky_occurrences": 23,
      "execution_groups": 4120, "flakiness_rate": 0.0056, "cost_score": 15230.0 }
  ]
}
```

**Acceptance:**
- [ ] 400 for an unknown `group_by`
- [ ] Numbers equal the same query against `reporting.v_flaky_tests` (test compares them)

### 7.4 Shadow decisions (REQ-6.4)

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/v1/quarantine` | Service token |

**Request:** `decision` (`shadow`; other values reserved for M3), `outcome`, filters from §8, `limit`, `cursor`.

**Response:**
```json
{
  "items": [
    { "test_id": 812, "test_key": "...", "team": "payments", "product_area": "checkout", "level": "api",
      "shadow_outcome": "auto_quarantine", "rate": 0.071, "occurrences": 3, "reason_suggested": "timing",
      "decided_at": "2026-11-20T03:13:02Z", "evidence_runs": ["https://github.com/.../runs/11893422/attempts/2"] }
  ],
  "next_cursor": null
}
```

**Acceptance:**
- [ ] Only open shadow decisions by default; `include_closed=true` returns history

---

## 8. Filter Parameters

Shared by the read API and mirrored by Grafana variables.

| Param | Type | Description | Default |
|-------|------|-------------|---------|
| `repo` | string (repeatable) | Repository full name | all |
| `team` | string (repeatable) | Team slug, including `unowned` | all |
| `product_area` | string (repeatable) | Area name, `unassigned` for none | all |
| `level` | enum | unit, integration, api, e2e, unclassified | all |
| `framework` | enum | pytest, playwright, jest | all |
| `reason` | enum | the 9 reasons of §4.2 | all |
| `from`, `to` | ISO date | Time range | last 14 days |
| `data` | enum | `real`, `demo`, `all` (by `repositories.is_demo`) | `real` |

**Acceptance:**
- [ ] One pydantic model parses these for every endpoint
- [ ] `from` after `to` → 400

---

## 9. Error Responses

| Endpoint | Cause | Status |
|----------|-------|--------|
| Read API | Missing / wrong service token | 401 |
| Read API | Invalid filter value type, `from` > `to`, bad `group_by` | 400 |
| `/tests/{id}/history` | Unknown test | 404 |
| Webhook | Bad signature | 401 |
| Any | Unexpected error | 500 with a generic body; details in logs with `request_id` |

---

## 10. Configuration Keys Used

| Key (`teams.yaml` → `defaults`) | Default | Used by |
|---------------------------------|---------|---------|
| `flakiness_threshold` | 0.05 | REQ-4.2 |
| `min_flaky_occurrences` | 2 | REQ-4.2 |
| `rate_method` | simple | REQ-4.2 |
| `window_days` / `window_min_executions` | 14 / 30 | REQ-4.1 |
| `team_cap` | 0.05 | REQ-5.2 |
| `team_cap_min_tests` | 1 | REQ-5.2 floor |
| `mass_failure.ratio` / `min_tests` / `single_fingerprint_tests` | 0.20 / 50 / 25 | REQ-2.4 |
| `inventory_stale_days` | 30 | REQ-5.2 active tests |

Settings (env): `FQ_READ_API_TOKEN`, `FQ_GITHUB_WEBHOOK_SECRET`, `FQ_CONFIG_REPO`, `FQ_CODEOWNERS_CACHE_TTL_S`.

---

## 11. Implementation Order

| Phase | Scope | Dependencies |
|-------|-------|--------------|
| **0** | Contracts: domain input/output dataclasses, view column lists | — |
| **1** | Pure domain: fingerprint, classifier, mass failure, evidence, rates, policy, state machine | Phase 0 |
| | Ownership: CODEOWNERS parser, resolver | Phase 0 |
| | Data: migration 0004, repositories, reporting views (0005) | Phase 0 |
| **2** | Config sync job + webhook | Ownership |
| | Daily aggregation job | Data |
| **3** | Detection tasks: classify run → evidence → evaluate candidate → shadow record | Phases 1–2 |
| **4** | Read API | Data, Phase 3 for realistic tests |
| **5** | Seeder derive step, end-to-end test, docs | All |

---

## 12. Aggregation Pipelines (Summary)

PostgreSQL queries and views (no ORM loops):

- **Cross-run evidence lookup:** for each failed execution in the new run, `EXISTS` a passed execution of the same `test_id` in a run with the same `repository_id`, `commit_sha`, `environment`, not environmental, within the partition range of the last 30 days (and the reverse for a new pass).
- **Execution groups in window:** `COUNT(DISTINCT (commit_sha, environment))` per test over `test_executions JOIN ci_runs`, restricted by `executed_at`; compare 14-day count with the last 30 groups using a window function (`ROW_NUMBER() OVER (PARTITION BY test_id ORDER BY max(executed_at) DESC)`).
- **Occurrences in window:** `COUNT(*)` from `flaky_events` with `detected_at` in the chosen window.
- **Wilson lower bound:** computed in Python from (occurrences, groups) — not in SQL.
- **Cost:** `SUM(failed attempts)` × `percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms)` + `red_builds_caused × 600`.
- **Daily stats:** `INSERT ... SELECT ... GROUP BY test_id, day ON CONFLICT (day, test_id) DO UPDATE`; flips with `LAG(outcome) OVER (PARTITION BY test_id ORDER BY executed_at)` on default-branch runs.
- **Mass failure:** per run, `failed_count / test_count`, and `MAX(COUNT(*)) GROUP BY failure_signature_id`.

**Reporting views (column contract for Grafana):**

| View | Columns |
|------|---------|
| `v_flaky_tests` | test_id, repo, is_demo, test_key, framework, level, team, product_area, environment, state, is_protected, reason_suggested, reason_confirmed, flakiness_rate, flaky_occurrences, execution_groups, cost_score, last_flaky_at |
| `v_flakiness_daily` | day, repo, is_demo, team, product_area, level, executions, failures, flaky_occurrences, flips, rerun_seconds, flakiness_rate |
| `v_shadow_decisions` | test_id, repo, is_demo, test_key, team, product_area, level, shadow_outcome, rate, occurrences, reason_suggested, decided_at, evidence_run_url, team_active_tests, team_would_quarantine |
| `v_environmental_runs` | week, repo, is_demo, runs, environmental_runs, ratio |

---

## 13. Non-Functional Requirements

- Detection for one upload of 5,000 executions completes in under 10 seconds after parsing (measured on docker-compose).
- Detection queries touch only partitions inside the window (verified with `EXPLAIN`).
- Read API p95 under 300 ms on the seeded dataset.

---

## 14. Acceptance Criteria Summary

### Ownership & Config
- [ ] Team, area, level and protected flag resolved for every test; `unowned` and "unclassified" fallbacks work
- [ ] Config sync via webhook and cron; invalid config never replaces a valid one

### Classification
- [ ] Stable fingerprints; infra failures excluded; reasons suggested
- [ ] Environmental runs flagged and excluded from evidence; weekly ratio available

### Evidence & Rates
- [ ] Rerun and cross-run evidence on any branch, same SHA + environment only, one per group
- [ ] Window, threshold (rate and min occurrences), Wilson option, cost score
- [ ] Daily stats idempotent; flips counted

### Policy (Shadow)
- [ ] Protected → cap → auto order; shadow records with outcome; zero external calls
- [ ] One open shadow decision per test; state machine enforced

### Read API
- [ ] 4 endpoints with shared filters, pagination, 400/401/404 handling
- [ ] Numbers match the reporting views

### Quality
- [ ] Domain coverage ≥ 90%; integration tests for every repository, job and route
- [ ] New tests pass 10 times in a row and in random order
