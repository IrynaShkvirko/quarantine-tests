# Feature: AI Failure Triage (Future Improvement)

**Status:** Proposed — not scheduled · **Earliest:** after M4 (needs Jira tickets and the quarantine lifecycle) · **Architecture:** §4.2 (reasons), §4.7 (product-bug path), §13 (security), §18 (future improvements)

## Summary

Today a flaky test's reason is suggested by regex rules (`reason_rules.yaml`), and many tests end up `untriaged`. This improvement adds an LLM step: when a test becomes a quarantine candidate and the rules can't classify it confidently, the worker sends the evidence — masked stack traces of failing attempts, a passing attempt for contrast, the test's source at that commit and recent changes to it — to an LLM and gets back a suggested reason, a likely root cause and a suggested fix.

[Headroom](https://github.com/headroomlabs-ai/headroom) compresses that evidence in-process before the call, so prompts stay small and cheap. Its log compressor keeps errors, stack traces and summaries and drops passing noise; it runs offline, and only the compressed prompt goes to the model provider.

The result lands in the Jira ticket and on the dashboard. A human still confirms the reason, as today.

## Decisions (proposed)

- **Rules first, LLM second.** The LLM runs only for `untriaged` tests or rule matches below a confidence level, so routine cases cost nothing.
- **Advisory only.** The LLM never changes state, never quarantines or releases a test, and never sets the confirmed reason.
- **Masked data only.** Prompts are built from the masked text stored at ingestion (§13); raw uploads are never read.
- **Headroom in library mode** (`headroom-ai`, in-process `compress()`, `HEADROOM_OFFLINE=1`): no proxy to run, no extra network calls.
- **One provider behind an interface.** Anthropic Claude as the default implementation of an `LLMClient` Protocol, so another provider can be added later.
- **Budgeted.** A daily token budget and a per-test cap; when the budget runs out, triage waits until the next day.
- **Shadow-mode compatible.** In shadow mode the triage runs and is shown on the dashboard, without touching Jira.

## General Rules

- **REQ-0.1:** Triage is off by default and enabled per repo (`ai_triage.enabled`).
- **REQ-0.2:** Every triage result is labeled as AI-suggested wherever it's shown (Jira, dashboards, digest).
- **REQ-0.3:** A failed or timed-out LLM call never blocks the quarantine flow; the test simply has no AI suggestion.
- **REQ-0.4:** Prompt and response are stored (masked) with the model name, token counts and cost, so results can be audited and evaluated.

---

## Product Requirements

### 1. When triage runs

- **REQ-1.1:** Triage runs when a test becomes a candidate (shadow or enforce) and its suggested reason is `untriaged`, or the matching rule is marked low-confidence.
- **REQ-1.2:** Triage runs again when a quarantined test re-flakes with a new fingerprint.
- **REQ-1.3:** A test is triaged at most once per fingerprint unless someone asks for a re-run (Jira label `ai-retriage`).

### 2. Evidence sent to the model

- **REQ-2.1:** Up to 3 failing attempts (masked message and stack trace), 1 passing attempt, the environment and the evidence type (rerun / cross-run).
- **REQ-2.2:** The test's source file at the failing commit, fetched through the GitHub contents client.
- **REQ-2.3:** The diff of the test file over the last 30 days, if any.
- **REQ-2.4:** Captured stdout/stderr from JUnit `system-out` / `system-err` when the reporter included it.
- **REQ-2.5:** All of it is compressed with Headroom before the call (log compressor for traces and output, diff compressor for diffs, code compressor for source); the prompt stays under `ai_triage.max_input_tokens` (default 8,000).

### 3. What comes back

- **REQ-3.1:** Structured output (validated with a schema): `reason` (one of the 9 in §4.2), `confidence` (0–1), `root_cause` (≤ 3 sentences), `suggested_fix` (≤ 5 bullets), `evidence_lines` (quoted lines from the input).
- **REQ-3.2:** Output that fails validation, names a reason outside the list, or quotes lines not in the input is discarded and logged.
- **REQ-3.3:** `reason = product_bug` with confidence ≥ 0.7 adds a note to the ticket suggesting the product-bug path (§4.7); it doesn't start it.

### 4. Where results appear

- **REQ-4.1:** Jira: an "AI triage" section in the ticket description (or a comment if the ticket exists), plus the label `flaky-reason-ai:<reason>`.
- **REQ-4.2:** Grafana: AI-suggested vs rule-suggested vs confirmed reason on the Flaky tests dashboard; agreement rate between AI suggestion and confirmed reason.
- **REQ-4.3:** Weekly digest: number of tests triaged and how many AI suggestions were confirmed.

### 5. Cost and safety controls

- **REQ-5.1:** Daily token budget (`ai_triage.daily_token_budget`) and per-test cap; usage shown on the CI cost dashboard.
- **REQ-5.2:** The secret-masking rules run again on the final prompt; any remaining match aborts the call.
- **REQ-5.3:** The provider API key lives in the secret manager like the other credentials; calls have timeouts and bounded retries.
- **REQ-5.4:** Token savings from Headroom are recorded per call (`tokens_before`, `tokens_after`).

### 6. Quality measurement

- **REQ-6.1:** A labelled set built from the demo flaky tests (one per reason) runs in CI against a recorded model response; a change to prompts or compression must keep accuracy on it.
- **REQ-6.2:** The agreement rate between AI-suggested and human-confirmed reasons is tracked over time (target to be set after a first month of data).

---

## Out of Scope (Not Included in This Improvement)

- Automatic fixes or PRs that change test code
- Using the LLM for the quarantine decision itself (detection stays rule-based and deterministic)
- Collecting full CI job logs beyond what JUnit already carries
- Running a local / self-hosted model (possible later behind the same `LLMClient` interface)

---

## Architecture Impact (when scheduled)

| Area | Change |
|------|--------|
| Worker | New task `triage_candidate(test_id, fingerprint)` enqueued after a candidate decision or re-flake |
| Integrations | `integrations/llm/` — `LLMClient` Protocol, Anthropic implementation, fake for tests |
| Compression | `headroom-ai` dependency; `domain/triage_prompt.py` builds the evidence bundle, Headroom compresses it |
| Data | New table `ai_triage_results` (test, fingerprint, model, tokens before/after, cost, output, status); reporting view `v_ai_triage` |
| Config | `ai_triage: { enabled, model, max_input_tokens, daily_token_budget, min_rule_confidence }` in `teams.yaml` defaults / repo overrides |
| Security | New trust boundary: masked evidence sent to the LLM provider; prompt re-masking; provider key handling (§13) |
| Docs | New page "AI failure triage" under How Detection Works; configuration and dashboard updates |

## Open Questions

1. Should triage also run for protected-flaky tests (they're never quarantined, but often the most important)?
2. Is test source code allowed to leave the network for every repo, or should source be an opt-in per repo?
3. Which confidence threshold makes an AI suggestion visible on the dashboard by default?
