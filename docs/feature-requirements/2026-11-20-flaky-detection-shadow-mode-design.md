# Feature: Flaky Test Detection (Shadow Mode)

**Milestone:** M2 · **Issues:** M2-01 to M2-13 · **Architecture:** §3, §4.1, §4.2, §4.11, §4.12, §5, §10, §12, §15

## Summary

The system starts judging tests. After each CI upload is parsed (M1), every failure is fingerprinted and classified, every test is given an owner, a product area and a level, and same-commit pass/fail evidence is turned into flaky occurrences and a flakiness rate. The policy engine then decides what it **would** do with each candidate: quarantine it automatically, ask the lead because the team is over its cap, or raise an alert because the test is protected.

In this feature nothing leaves the system: no bot PRs, Jira tickets or Slack messages. Decisions are recorded and shown on two Grafana dashboards (Flaky tests, Shadow mode). This is the shadow period from §4.12. It lets us tune thresholds and infra signatures on real data before enforcing anything in M3.

## Decisions

- **Shadow only.** Every repo runs in `mode: shadow`. Enforce mode, bot PRs, Jira and Slack come in M3.
- **Event-driven detection.** Detection runs in the worker right after an upload is parsed. A nightly job recomputes daily stats and cost scores.
- **Pure domain.** Fingerprinting, classification, evidence, rates, policy and the state machine are pure functions in `backend/app/domain/`, written test-first.
- **Ownership from CODEOWNERS at the commit SHA**, mapped to teams through `teams.yaml`. No match goes to the `unowned` team.
- **Grafana first.** Dashboards read only `reporting.*` views. A read API is built now for the future UI (M7) and for scripts, but it is internal-only.
- **Shadow decisions count toward the team cap.** Open "would auto-quarantine" decisions are added to quarantined tests when checking the 5% cap, so the shadow numbers match what enforce mode would do (architecture D9).
- **Flips on the default branch only** (nightly runs included). Same-commit changes on PRs are already flaky evidence (architecture D36).
- **"Unclassified" is a visible level, never a config error.** Config sync warns, dashboards and the digest show it, verification uses 25 repetitions (D37).
- **Cap with a floor, on active tests.** Allowed quarantined tests per team per repo = max(5% × tests seen in the last 30 days, 1) (D38).
- **Demo data is part of the feature.** Deliberately flaky demo tests and a 28-day history seeder make every panel meaningful from day one, and all of it can be deleted with one command.

## General Rules

- **REQ-0.1:** All decision logic lives in `backend/app/domain/` with no I/O and no clock. Time is passed in.
- **REQ-0.2:** Every threshold comes from configuration (`teams.yaml` defaults, §5.1; repo overrides in `quarantine-policy.yaml`). Nothing is hardcoded.
- **REQ-0.3:** Detection never runs in the request path. It runs in Procrastinate tasks and cron jobs.
- **REQ-0.4:** Reprocessing the same upload, or running a task twice, produces the same rows and the same decisions (idempotent).
- **REQ-0.5:** Timestamps are stored in UTC. Dashboards display Europe/Kyiv.
- **REQ-0.6:** All dashboard text (titles, panel names, legends, descriptions) is in English. Numbers and dates use en-US format (1,234 · Nov 20, 2026). Rates show one decimal (5.1%).
- **REQ-0.7:** Failure text used anywhere in this feature is the masked text stored at ingestion (§13). Raw messages are never re-read.

---

## Product Requirements

### 1. Ownership, Product Area and Level

- **REQ-1.1:** Each test is assigned a team from the repo's CODEOWNERS file at the run's commit SHA, using GitHub's rules (the last matching pattern wins). The GitHub team is mapped to a team through `teams.yaml`.
- **REQ-1.2:** A test with no CODEOWNERS match, or a match to a GitHub team that isn't in `teams.yaml`, belongs to the `unowned` team.
- **REQ-1.3:** Each test is assigned a product area from the `paths` globs of its team in `teams.yaml`. No match → product area "Unassigned".
- **REQ-1.4:** Each test is assigned a level (unit, integration, api, e2e) from the path rules first and the CI job name rules second. No match → "unclassified". This never makes `teams.yaml` invalid; config sync logs a warning with the number of unclassified tests per repo.
- **REQ-1.5:** A test is protected if `quarantine-policy.yaml` lists its path, its ID or one of its markers, or if a marker in the JUnit properties matches.
- **REQ-1.6:** `teams.yaml` is loaded from the config repo on every push to it (webhook) and at least every 15 minutes. An invalid file is rejected, the previous configuration stays active, and the error is logged and counted.

### 2. Failure Classification

- **REQ-2.1:** Every failure gets a fingerprint: masked message with numbers, UUIDs, timestamps, temp paths and memory addresses removed, combined with the exception type and hashed. The same failure with different IDs or times gets the same fingerprint.
- **REQ-2.2:** Failures matching an infra signature (runner OOM, browser crash, image pull error, lost runner) are classified `infra` and never count as flaky evidence.
- **REQ-2.3:** Every non-infra failure gets a suggested reason from `reason_rules.yaml` (first matching rule wins). No match → `untriaged`.
- **REQ-2.4:** A run is marked environmental when more than 20% of its tests fail (only for runs with at least 50 tests), or when one fingerprint fails 25 or more tests. Its failures are stored, but none of them count as evidence.
- **REQ-2.5:** The share of environmental runs per repo per week is available on the dashboard.

### 3. Flaky Evidence

- **REQ-3.1:** A test that fails and then passes within one execution (framework rerun) produces `rerun` evidence, on any branch.
- **REQ-3.2:** A test that fails in one run or run attempt and passes in another, on the same commit SHA and environment, produces `cross_run` evidence, on any branch.
- **REQ-3.3:** Results on different SHAs or different environments are never paired as evidence.
- **REQ-3.4:** Each `(test, commit SHA, environment)` group produces at most one flaky occurrence, however many uploads or reprocessings touch it.
- **REQ-3.5:** Evidence is recorded for protected tests too. Protection affects the decision, not the detection.

### 4. Flakiness Rate and Cost

- **REQ-4.1:** The window is whichever has more execution groups: the last 14 days or the last 30 execution groups.
- **REQ-4.2:** Flakiness rate = flaky occurrences ÷ execution groups in the window. The threshold is met when the rate is above 5% **and** there are at least 2 flaky occurrences. A repo can switch to the Wilson lower bound (`rate_method: wilson`).
- **REQ-4.3:** Each test has a cost score = failed attempts in the window × median duration + red builds caused × 10 minutes.
- **REQ-4.4:** A nightly job writes `daily_test_stats` per test per day (executions, failures, flaky occurrences, rerun seconds, red builds caused, flips). Running it twice for the same day gives the same rows.
- **REQ-4.5:** Flips (pass↔fail changes between consecutive executions) are counted per day for trend panels, on the default branch only (nightly runs included). PR branch runs are not counted.

### 5. Policy and State (Shadow)

- **REQ-5.1:** A test with a flaky occurrence becomes **Candidate** when the threshold is met and **Watching** when it isn't. A Watching test with no occurrence in the window returns to **Healthy**.
- **REQ-5.2:** For each candidate, the policy decides in this order: protected → `protected_alert`; team over cap → `needs_lead_approval`; otherwise → `auto_quarantine`. Over cap means quarantined + open would-auto-quarantine tests ≥ allowed, where allowed = max(5% × active tests, 1) for the team in that repo, and active = seen in the last 30 days.
- **REQ-5.3:** In shadow mode the decision is recorded as a quarantine record with `decision = shadow` and its outcome, and the test returns to Watching. No PR, ticket or message is created.
- **REQ-5.4:** Every decision record stores the rate, occurrences, window, suggested reason, fingerprint and links to the CI runs that produced the evidence.
- **REQ-5.5:** A test gets at most one open shadow decision. A new decision is recorded only when the outcome changes or the previous one is older than the window.
- **REQ-5.6:** Every state change goes through the state machine (§11). An illegal transition is rejected and logged, never forced.

### 6. Read API (internal)

- **REQ-6.1:** List tests with filters (repo, team, product area, level, framework, state, protected) and their current rate, occurrences and cost.
- **REQ-6.2:** Show one test's history: executions by run and run attempt, flaky events, decisions.
- **REQ-6.3:** Return flakiness statistics grouped by team, product area, level, reason or environment.
- **REQ-6.4:** List shadow decisions with filters.
- **REQ-6.5:** The read API is reachable only inside the cluster and requires a service token until the UI's OAuth exists (M7).

### 7. Dashboards (Grafana)

- **REQ-7.1:** A **Flaky tests** dashboard shows flaky tests by level, by reason (suggested vs confirmed) with the product area, the top 10 by cost score, flaky tests by environment, the flakiness rate trend, and environmental runs per repo.
- **REQ-7.2:** A **Shadow mode** dashboard shows what enforce mode would have done: decisions per team and outcome, the would-be quarantined share per team against the 5% cap, protected-flaky tests, and a decision list with links to the evidence runs.
- **REQ-7.3:** Both dashboards have variables: repo, team, product area, level, framework, reason, time range, data (real / demo / all, default real).
- **REQ-7.4:** Clicking a test anywhere opens the Test drill-down dashboard filtered to that test.
- **REQ-7.5:** When demo data is shown, a "DEMO DATA" banner is visible on every dashboard.
- **REQ-7.6:** Panels with no data show a short explanation ("No flaky tests in this range") instead of an empty frame or an error.
- **REQ-7.7:** The Test inventory dashboard gets an "Unclassified tests" panel listing tests with no level, by repo and team.

### 8. Demo Data

- **REQ-8.1:** `fq-demo-shop-api` contains at least one deliberately flaky test per reason (timing, order dependency, concurrency, external dependency, test data / environment, nondeterminism, CI infrastructure, product bug), marked `demo_flaky`, with flake rate set by `FQ_DEMO_FLAKE_RATE` (default 0.2).
- **REQ-8.2:** The CI infrastructure demo test produces an OOM-like failure that the classifier must filter out.
- **REQ-8.3:** `fq-admin seed-demo --days 28 --runs-per-day 3` generates history for the demo repos: runs, shards, run attempts, executions, environmental runs, then derives evidence, stats and shadow decisions through the real detection code.
- **REQ-8.4:** Volume after seeding: at least 300 tests across both demo repos, at least 20 flaky tests spread over all reasons, at least 5 protected tests (2 of them flaky), at least 3 unowned tests, at least 2 environmental runs, and at least one team over its cap.
- **REQ-8.5:** Every panel on both dashboards shows data for every team and every level filter.
- **REQ-8.6:** All seeded rows belong to repositories with `is_demo = true` and carry a `seed_batch_id`. Seeding the same batch twice changes nothing. Seeding finishes in under 2 minutes.

### 9. Observability

- **REQ-9.1:** Metrics: time from upload to evaluated, flaky occurrences recorded, environmental runs, shadow decisions by outcome, config sync failures.
- **REQ-9.2:** Every decision is logged once with `test_id`, `upload_id`, outcome and the numbers it was based on.

---

## Out of Scope (Not Included in This Feature)

- Bot PRs, `quarantine.yaml` changes, Jira tickets, Slack messages (M3)
- Enforce mode and the separate quarantine CI job (M3)
- Verification, probation, SLA, max age, product-bug path (M4)
- Playwright and Jest normalizers (M5). Detection works on any normalized execution, but M2 is tested with pytest data
- Renamed / orphaned tests and manual skips (M5)
- Slack alert for a high environmental-run ratio (M3, when Slack exists). M2 provides the metric and panel
- Custom UI (M7)

---

## Open Questions

None open. Resolved on 2026-11-20: shadow decisions count toward the cap, flips on the default branch only, unclassified is a visible level, the cap uses active tests with a floor of 1 (architecture D9, D36–D38).
