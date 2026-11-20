---
name: security
description: "Security rules for the flaky test quarantine system, based on OWASP Top 10:2025 — threat model, ingestion API and repo tokens, webhook signatures, untrusted JUnit XML and gzip uploads, YAML config, secret masking, GitHub App / Jira / Slack credentials, fq-cli subprocess calls, GitHub Actions and Jenkins hardening, Postgres and Grafana access. Use when reviewing or writing code that handles input from CI jobs, webhooks or repo files, credentials, workflows or deployment config."
---

# Security — Flaky Test Quarantine System

Stack: FastAPI + pydantic, SQLAlchemy/Postgres, Procrastinate, httpx, Python `fq-cli`, TypeScript reporter plugins, GitHub Actions + Jenkins, GitHub App, Jira Cloud, Slack, Grafana, Kubernetes. See `examples.md` for unsafe/safe pairs, `checklists.md` for per-change checklists, `references.md` for sources. Architecture §13 is the agreed security design.

---

## Threat Model

| Entry point | Who controls the input | Main risks |
|-------------|------------------------|------------|
| `POST /api/v1/ingest/runs` | Any CI job holding a repo token (including jobs on PRs from forks) | Forged results for another repo, XML attacks (XXE, entity expansion), decompression bombs, oversized uploads, secrets inside stack traces |
| `POST /api/v1/webhooks/github` | Internet; trusted only after HMAC check | Forged "PR merged" events driving state transitions, replay |
| `POST /api/v1/webhooks/jira` | Internet; trusted only after secret check | Forged "Done" events releasing tests from quarantine |
| `GET /api/v1/repos/*/quarantine-plan` | CI jobs with a repo token | Reading another repo's plan |
| `quarantine.yaml`, `quarantine-policy.yaml` in app repos | Anyone who can open a PR in that repo | Disabling protection, injection into regexes or shell when building test selections |
| `teams.yaml` in the config repo | QA / platform owners | Lower risk, still validated |
| GitHub App private key, Jira token, Slack token | Operators (secret manager) | Leak → merge rights on repos, write access to Jira/Slack |
| GitHub Actions workflows / Jenkins library | Workflow authors; event data from PRs | Script injection, over-privileged `GITHUB_TOKEN`, secret exposure to fork PRs |
| Grafana | Org members via GitHub OAuth | Over-broad DB access, data from other teams |

**The two crown jewels:** the GitHub App key (can change `main` in every installed repo) and the state machine (decides which tests block builds). Protect both first.

---

## Confidence-Based Review

Before flagging, trace the data flow and confirm who controls the input.

| Confidence | Criteria | Action |
|------------|----------|--------|
| **HIGH** | Vulnerable pattern + input controlled by a CI job, webhook sender or repo file | Report with file, line, exploit and fix |
| **MEDIUM** | Vulnerable pattern, input source unclear | Note for manual verification |
| **LOW** | Theoretical / best-practice deviation | Don't report unless asked |

**Don't flag:** test code, values from `Settings` or our own constants, SQLAlchemy expressions with bound parameters, pydantic-validated fields used within their validated type.

> Golden rule: `settings.jira_base_url` = trusted. A test name from an uploaded JUnit file = untrusted, everywhere it goes (DB, regex, shell, Jira, Slack, YAML).

---

## OWASP Top 10:2025 for This System

| # | Category | Where it bites here |
|---|----------|---------------------|
| A01 | Broken Access Control | Repo token used to write another repo's runs; plan endpoint leaking other repos; Grafana role too broad |
| A02 | Security Misconfiguration | Public ingress exposing more than ingest/webhooks/plan; debug on in prod; Grafana anonymous access |
| A03 | Supply Chain Failures | Unpinned GitHub Actions; typosquatted PyPI/npm packages; plugins running inside users' test processes |
| A04 | Cryptographic Failures | Plain-text repo tokens; non-constant-time comparisons; weak webhook secrets |
| A05 | Injection | XXE in JUnit; SQL via string formatting; shell injection in fq-cli; regex injection in Playwright/Jest selection; workflow expression injection |
| A06 | Insecure Design | No size/decompression limits; bot allowed to change files other than `quarantine.yaml`; no rate limits on ingest |
| A07 | Authentication Failures | Missing token check on a route; webhook processed before signature check; fail-open dependency |
| A08 | Integrity Failures | Unvalidated `quarantine.yaml` merged by the bot; mass assignment from metadata; replayed webhooks |
| A09 | Logging Failures | Tokens or unmasked stack traces in logs, Jira tickets or Slack messages; no audit of quarantine decisions |
| A10 | Exceptional Conditions | Errors that grant access or skip checks; parse failures that crash the worker in a loop |

---

## A01 — Access Control

- **Deny by default.** Every route except `/healthz`, `/readyz` and webhooks requires a repo token (or OAuth for the future UI). Webhooks require a valid signature instead.
- **Bind data to the token's repository.** The repository in the upload metadata must equal the token's repository; reject mismatches with 403. Never trust `repository` from the body to pick where data goes.
- The quarantine plan endpoint returns only the token's repository.
- Grafana uses the `grafana_ro` role with `SELECT` on the `reporting` schema only.
- Lead-only actions (future UI decisions) check the role server-side.

## A02 — Configuration

- Public ingress exposes only `/api/v1/ingest/*`, `/api/v1/webhooks/*`, `/api/v1/repos/*/quarantine-plan` (§13). Everything else is internal.
- FastAPI docs (`/docs`, `/openapi.json`) disabled or internal-only in prod.
- No CORS until the UI exists; then an explicit origin allowlist.
- Grafana: anonymous access off, GitHub OAuth restricted to the org, admin password from the secret manager.
- Postgres: TLS, no public endpoint, app role without superuser.

## A03 — Supply Chain

- `uv.lock` and `pnpm-lock.yaml` committed; CI installs with `--frozen` / `--frozen-lockfile`.
- `pip-audit` and `pnpm audit` in CI; Dependabot weekly.
- Pin third-party GitHub Actions **by full commit SHA**, not tag.
- Our reporter plugins run inside users' test processes: zero runtime dependencies where possible, no network calls, no `postinstall` scripts.
- Before adding a dependency: maintained in the last 6 months, widely used, correct name, license compatible (MIT/Apache/BSD).

## A04 — Cryptography and Secrets

- **Repo tokens:** 32+ random bytes (`secrets.token_urlsafe(32)`), shown once, stored as SHA-256 hash; compared with `hmac.compare_digest`.
- **GitHub webhooks:** verify `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the webhook secret) with `hmac.compare_digest`.
- **Jira webhooks:** shared secret in a header or URL token, compared in constant time, plus the IP allowlist (§13).
- **GitHub App:** private key only in the secret manager; installation tokens are short-lived — request per operation, never store.
- Secrets come from `Settings` (env / External Secrets), never from repo files or the DB.
- TLS everywhere outside the cluster.

## A05 — Injection

### Untrusted XML (JUnit uploads)
- Parse with `defusedxml` (or `lxml` with `resolve_entities=False`, `no_network=True`, `huge_tree=False`). Never `xml.etree` / `minidom` directly on uploads.
- Reject DTDs; cap element count and attribute/text length.

### SQL
- SQLAlchemy expressions or `text()` with bound parameters only. Partition and schema names come from code.

### Shell (fq-cli, workflows, Jenkins)
- `subprocess.run([...])` with an argument list; never `shell=True`; never put test names, branch names or PR titles into a command string.
- Groovy: `sh(script: ..., returnStdout: true)` with values passed as environment variables, not string interpolation.

### Regex (test selection)
- Test names and titles used in Playwright `grep` / Jest `-t` patterns are escaped (`re.escape` in Python, an escape helper in TS). Prefer passing the list via a file (`FQ_QUARANTINE_FILE`) over building one giant regex.
- Regexes from config (`reason_rules.yaml`, `masking_rules.yaml`) are compiled once at load, with a length cap; patterns come only from the config repo.

### YAML
- `ruamel.yaml` safe mode / `yaml.safe_load` only. Then validate with pydantic (`extra="forbid"`).

### GitHub Actions expressions
- Never `run: echo "${{ github.event.pull_request.title }}"`. Pass through `env:` and quote: `run: echo "$TITLE"`.

## A06 — Insecure Design

- **Size limits:** per-part and total upload size (`FQ_INGEST_MAX_UPLOAD_MB`), checked while streaming; **decompressed size** of gzip parts capped (e.g. 10× compressed and an absolute max).
- **Rate limits** per repo token on ingest and plan endpoints; `429` with `Retry-After`.
- **Bot scope:** the bot PR check enforces "only `quarantine.yaml` changed"; rulesets let the App bypass review only (§9.5). Any widening is CRITICAL.
- **Protected tests** can never be quarantined, even if a crafted `quarantine.yaml` lists them (bot check + backend policy both enforce it).
- **Fork PRs:** reusable workflows never expose the repo token or other secrets to `pull_request` runs from forks; uploads from forks are skipped or go through a token-less path.

## A07 — Authentication

- Token check is a FastAPI dependency that raises `401` on any failure; it never returns `None` to mean "anonymous".
- Webhook routes read the raw body, verify the signature, **then** parse JSON. Invalid signature → `401`, no DB access, no logging of the payload.
- Webhook replay: dedupe on `X-GitHub-Delivery` / Jira event ID and ignore events older than a short window where timestamps exist.

## A08 — Data Integrity

- Upload metadata and config are pydantic models with `extra="forbid"`; unknown fields are rejected, not silently stored.
- State changes come only from validated transitions in the state machine; webhook payloads can't set state directly.
- `quarantine.yaml` entries are re-validated by the backend when read, even after the bot check passed.

## A09 — Logging and Masking

- **Mask before storing:** failure messages and stack traces from uploads go through the masking rules (§13) **before** they're written anywhere — raw uploads included.
- Text sent to Jira or Slack comes from masked data only.
- Never log tokens, `Authorization` headers, webhook secrets, App keys or full payloads.
- **Audit log:** every quarantine decision, state transition, bot PR and manual decision is recorded with actor, time and reason (these are the `quarantine_records` / `quarantine_decisions` rows — keep them complete).
- Log auth failures (repo, IP, reason) at warning level; alert on spikes.

## A10 — Exceptional Conditions

- **Fail closed:** any exception in auth or signature checks → reject.
- A malformed upload marks that upload `failed` with an error summary; it must not crash the worker or retry forever (poison message → fail after N attempts).
- External service down → state stays consistent and the task retries; never skip a check to "keep going".
- Generic 5xx messages to clients; details only in logs.

---

## Secret Detection

Patterns to scan for in code, config, fixtures and also used by the masking rules:

| Type | Pattern |
|------|---------|
| GitHub token | `gh[pousr]_[A-Za-z0-9]{36,}` and `github_pat_[A-Za-z0-9_]{22,}` |
| Atlassian API token | `ATATT[A-Za-z0-9_\-=]{20,}` |
| Slack token | `xox[abposr]-[0-9A-Za-z-]+` |
| AWS access key | `AKIA[0-9A-Z]{16}` |
| JWT | `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` |
| Postgres URL with password | `postgres(ql)?(\+\w+)?://[^:\s]+:[^@\s]+@` |
| Private key | `-----BEGIN [A-Z ]*PRIVATE KEY-----` |
| Generic | `(secret\|token\|password\|api[_-]?key)\s*[:=]\s*['"][^'"]{8,}` |

**Never commit:** `.env`, `*.pem`, GitHub App keys, `kubeconfig`, real Jira/Slack exports.

---

## Python / FastAPI Quirks

- `xml.etree.ElementTree` is not safe for untrusted input — use `defusedxml`.
- `gzip.decompress()` on untrusted data has no size limit — stream with a cap.
- `yaml.load` without `SafeLoader` executes code.
- `subprocess` with `shell=True` interprets metacharacters.
- `hmac.compare_digest`, not `==`, for secrets and signatures.
- Reading `await request.json()` before verifying a webhook signature defeats the check — verify `await request.body()` first.
- pydantic `model_validate` with `extra="allow"` keeps attacker-supplied fields.

## GitHub Actions / Jenkins Quirks

- `pull_request_target` runs with secrets on fork code — don't use it to run tests.
- Default `GITHUB_TOKEN` permissions may be broad — set `permissions:` per workflow/job.
- `${{ }}` expressions in `run:` are template-expanded before the shell runs — injection point.
- Jenkins: Groovy string interpolation in `sh "..."` with user data is shell injection; use `withEnv` and single-quoted scripts.

---

## Severity Classification

| Severity | Criteria | Examples here |
|----------|----------|---------------|
| **CRITICAL** | Direct exploit, no special conditions | XXE in JUnit parsing; webhook processed without signature; bot can change files beyond `quarantine.yaml`; App key committed |
| **HIGH** | Exploitable with conditions | Repo A can write repo B's results; no decompression limit; workflow script injection via PR title; tokens in logs |
| **MEDIUM** | Limited impact | Missing rate limit; OpenAPI docs public; unpinned action by tag; verbose 5xx errors |
| **LOW** | Defense in depth | Missing alert on auth-failure spikes; long-lived Grafana sessions |

## Review Process

1. Identify the entry point(s) the change touches (threat model table).
2. Load the matching sections above and the checklist in `checklists.md`.
3. Trace each untrusted value to every sink (DB, regex, shell, XML parser, Jira, Slack, logs, workflow expression).
4. Check the controls in front of it (token dependency, signature check, schema, size limit, escaping).
5. Report HIGH-confidence findings with exploit and fix.
