# Spike M0-12: GitHub App auto-merge with ruleset bypass

**Status: prototype ready, scenarios NOT yet run.** The App, the `fq-sandbox` repo and the rulesets need to be created in a real GitHub account. Sections marked _pending_ get filled in when the scenarios run. Spec: `docs/architecture.md` §4.1, §9.5, §13.

**Question.** Can a GitHub App open a PR that changes only `quarantine.yaml` and have it auto-merge once `fq-quarantine-check` passes, with no human review, while every other PR on `main` still needs a review?

## App manifest

| Item | Value |
| --- | --- |
| Name | `fq-bot-dev` |
| Repository permissions | `contents: write`, `pull_requests: write`, `metadata: read`, `checks: read` |
| Webhook events | `pull_request`, `push` (+ `check_suite` only if the fallback is needed). Webhooks stay **disabled** in the spike; with a URL, set a webhook secret (§13) |
| Never grant | `workflows` permission. Without it the bot cannot edit the check workflow, so it cannot remove its own gate |
| Install on | `fq-sandbox` only |
| Private key | stored outside the repo (`~/.secrets/fq-bot-dev.pem`) |

Note: §9.5 (D29) lists three permissions. This spike adds `checks: read` (needed for the fallback path), so §9.5 must change if the fallback wins or the permission is kept.

## Ruleset layout under test

Two rulesets, so the bypass covers review only. Templates in `spikes/github-app/rulesets.json`.

- **A `review`:** require a PR with 1 approval. Bypass: the App, mode `pull_request`.
- **B `checks`:** require status check `fq-quarantine-check`. No bypass.

Exported ruleset JSON: _pending_ (`gh api repos/OWNER/fq-sandbox/rulesets/<id>`).

## Setup for a new repo

1. Settings → General → enable **Allow auto-merge**. (Required for `enablePullRequestAutoMerge`.)
2. Create the App (Settings → Developer settings → GitHub Apps) with the manifest above. Generate a private key, save it outside the repo.
3. Install the App on the target repo only.
4. Add `.github/workflows/fq-quarantine-check.yml` from `spikes/github-app/workflow/` and a seed `quarantine.yaml` on `main`. Merge them (before the rulesets exist).
5. Create ruleset A and B from `rulesets.json`, replacing `actor_id: 0` with the App id.
6. Run the prototype: `FQ_APP_ID=… FQ_APP_KEY_PATH=… uv run spikes/github-app/fq_bot.py --repo OWNER/REPO`.

_Timing check (acceptance: under 15 minutes on a second repo): pending._

## Scenario results

| # | Scenario | Expected | Actual |
| --- | --- | --- | --- |
| 1 | App PR changes only `quarantine.yaml` | check passes, auto-merges, no review | _pending_ |
| 2 | App PR also changes `README.md` (`--also-readme`) | check fails, no merge | _pending_ |
| 3 | Human PR changes only `quarantine.yaml` | needs a review | _pending_ |
| 4 | App PR while the check fails | stays open | _pending_ |

## Decision

_Pending._ Auto-merge, or App-driven merge (fallback: webhook `check_suite` completed → REST merge). Update §9.5 if the ruleset layout differs.

## Open items

**Before closing M0-12 (#12):**

- [ ] Run the four scenarios on `fq-sandbox` and fill in the results table.
- [ ] Export both rulesets from the API and paste the JSON above.
- [ ] Time the setup on a second repo (target: under 15 minutes).
- [ ] Record the decision: auto-merge or App-driven merge. If the fallback wins, add a `check_suite` handler and REST merge to the prototype.
- [ ] Decide on `checks: read`: drop it, or update §9.5 (D29) with agreement.
- [ ] Scenario 4: add a reliable way to make the check fail on a quarantine-only PR.

**Carry into M3-01 (the prototype is not production code):**

- [ ] Pin `actions/checkout` and every other action by full commit SHA.
- [ ] Extend `fq-quarantine-check` with §9.5 content validation: schema, known tests or pending renames, no protected tests, a Jira key on every entry.
- [ ] `put_file`: treat only 404 as "file missing"; raise on any other non-200.
- [ ] Pin the httpx and pyjwt versions. Add bounded retries with backoff that respect 429 / `Retry-After` (CLAUDE.md).
- [ ] Never overwrite `quarantine.yaml` wholesale. Edit the entries instead.
- [ ] Validate repo names from the DB with the same `OWNER/NAME` pattern.

## Things to watch

- `fq-quarantine-check` is the **only** control behind the review bypass. The spike check requires exactly one raw diff line, status `M`/`A`, mode `100644`, path `quarantine.yaml` (no deletes, renames or symlinks). M3 must add schema, protected-test and Jira-key validation (§9.5) before this goes near a real repo.
- Ruleset B pins the check to GitHub Actions (`integration_id` 15368) so nothing else can post a status with that name.
- The installation token is scoped to one repo with `contents` and `pull_requests` write only. Rotate the App key every 90 days (§9.5).
- `checks: read` is not in §9.5 (D29). Drop it if auto-merge wins; keep and update §9.5 if the fallback wins.
- Auto-merge on a PR the App opened: confirm the bypass applies when GitHub performs the merge, not only when the App merges directly.
- Scenario 4 needs a way to make the check fail on a quarantine-only PR (for example a temporary `exit 1` on a branch-specific condition).
