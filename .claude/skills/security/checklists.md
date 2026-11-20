# Security Checklists — Quick Reference

Run the checklist that matches each change before committing or opening a PR.

---

## Pre-Commit Self-Review (every change)

- [ ] No secrets, tokens, keys or real customer data in code, fixtures or docs
- [ ] No `.env`, `*.pem` or kubeconfig staged
- [ ] Untrusted input (uploads, webhooks, repo YAML) is validated before use
- [ ] No SQL built from strings; no `shell=True`; no unescaped values in regexes
- [ ] Errors to clients are generic; details only in logs
- [ ] Logs contain no tokens, auth headers or unmasked failure messages

---

## New or Changed API Route

### Auth
- [ ] Route requires a repo token (or OAuth) unless it's a health check or webhook
- [ ] Data is scoped to the token's repository; body fields can't redirect writes to another repo (403 on mismatch)
- [ ] Rate limit applies (ingest, plan)

### Input
- [ ] Request body / query are pydantic models with `extra="forbid"` and length limits
- [ ] Upload size checked while streaming; decompressed size capped
- [ ] Files parsed in the worker, not the request

### Errors and responses
- [ ] 400 / 401 / 403 / 413 / 429 returned where they apply
- [ ] 5xx bodies generic; no stack traces
- [ ] Response contains only what the caller needs

---

## Webhook Handler (GitHub / Jira)

- [ ] Raw body read and signature / secret verified with `hmac.compare_digest` **before** parsing or DB access
- [ ] Invalid signature → 401, payload not logged
- [ ] Delivery ID deduplicated; handler idempotent
- [ ] Only expected event types handled; others acknowledged and ignored
- [ ] Payload can't set state directly — it triggers a validated state-machine transition
- [ ] Jira: IP allowlist configured at the ingress

---

## Parsing Untrusted Files (JUnit XML, gzip, YAML)

- [ ] XML parsed with `defusedxml` (DTDs and entities rejected)
- [ ] Limits on element count, text length, number of test cases per upload
- [ ] gzip decompressed by streaming with an absolute size cap
- [ ] YAML loaded in safe mode, then validated with pydantic
- [ ] Failure messages masked **before** storage (raw upload included)
- [ ] Malformed file marks the upload `failed` with a summary; worker doesn't crash or retry forever
- [ ] Hypothesis / golden tests include hostile inputs (entity expansion, huge text, invalid UTF-8)

---

## External Integration (GitHub App, Jira, Slack)

- [ ] Credentials from `Settings` / secret manager only
- [ ] GitHub installation tokens requested per operation, not stored
- [ ] Least privilege: App permissions match §9.5 exactly; Jira/Slack tokens scoped to what's used
- [ ] Timeouts and bounded retries; 429 / `Retry-After` respected
- [ ] Text sent to Jira/Slack built from masked data; no tokens or internal URLs leaked
- [ ] Client errors mapped to our exceptions; tokens not included in exception messages

---

## Bot PR / quarantine.yaml Changes

- [ ] Bot check still enforces: only `quarantine.yaml` changed, schema valid, known tests, no protected tests, Jira key present
- [ ] Ruleset bypass for the App covers review only; required checks have no bypass
- [ ] Backend re-validates `quarantine.yaml` when reading it
- [ ] Nothing in the change widens what the App can write

---

## fq-cli / Plugins

- [ ] `subprocess.run([...])` with argument lists; no `shell=True`
- [ ] Test names escaped before use in Playwright `grep` / Jest `-t`; lists passed via file where possible
- [ ] Upload token read from env, never printed (mask in CI logs)
- [ ] Upload failures never change the build result and never print the token
- [ ] Plugins: no network calls, no runtime dependencies without reason, no `postinstall` scripts

---

## GitHub Actions Workflow / Jenkins Step

- [ ] `permissions:` set explicitly, least privilege
- [ ] Third-party actions pinned by full commit SHA
- [ ] No `${{ github.event.* }}` (titles, branch names, bodies) directly in `run:` — use `env:`
- [ ] No `pull_request_target` running untrusted code with secrets
- [ ] Repo token not available to fork PRs
- [ ] Secrets masked (`::add-mask::`) if derived at runtime
- [ ] Jenkins: values passed with `withEnv`, scripts single-quoted; no Groovy interpolation of user data

---

## Database Migration

- [ ] No credentials or data in the migration
- [ ] Grafana role keeps `SELECT` on `reporting` only
- [ ] App role has no superuser / DDL rights beyond what migrations need (separate migration role in prod)
- [ ] New tables holding failure text store masked data only

---

## New Dependency

- [ ] Needed — can't be done with the standard library or existing deps
- [ ] `pip-audit` / `pnpm audit` clean
- [ ] Maintained (last release within ~6 months), widely used, correct name (no typosquat)
- [ ] License compatible (MIT, Apache-2.0, BSD)
- [ ] Lockfile updated and committed
- [ ] For plugins: added to devDependencies unless it must run in users' test processes

---

## Deployment (Helm / Kubernetes)

- [ ] Ingress exposes only the public paths in §13
- [ ] Secrets via External Secrets, not values files
- [ ] Containers run as non-root, read-only root filesystem where possible
- [ ] Grafana: anonymous off, OAuth limited to the org
- [ ] Postgres not publicly reachable; TLS on
