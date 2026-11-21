# Spike M0-12: GitHub App auto-merge with ruleset bypass

**Status: run on 2026-11-21 against `IrynaShkvirko/fq-sandbox` and `IrynaShkvirko/fq-sandbox-2`.** Spec: `docs/architecture.md` §4.1, §9.5, §13.

**Question.** Can a GitHub App open a PR that changes only `quarantine.yaml` and have it auto-merge once `fq-quarantine-check` passes, with no human review, while every other PR on `main` still needs a review?

**Answer.** Not with GitHub auto-merge: **auto-merge does not apply the App's ruleset bypass.** The PR waits for a review forever. **App-driven merge works:** when the App calls the REST merge endpoint itself, the review bypass applies and the required check is still enforced. Decision: App-driven merge, where the bot verifies the PR itself before merging, because the required check alone can be rewritten by whoever pushes to the PR (see [Decision](#decision) and [Security review](#security-review-pre-merge-verification)).

## App manifest

Created with `spikes/github-app/create_app.py` (GitHub App manifest flow: one click in the browser; the key is written to `~/.secrets/<slug>.pem`, mode 600, never printed).

| Item | Value |
| --- | --- |
| Name | `fq-bot-dev-2` (App id 5866726). `fq-bot-dev` was taken; App names are global |
| Visibility | private (installable only on the owner's account) |
| Repository permissions | `contents: write`, `pull_requests: write`, `metadata: read`, `checks: read` |
| Webhook events | `pull_request`, `push` on `fq-bot-dev-2`; `create_app.py` now also subscribes to `check_suite`, which the chosen design uses. Webhooks stayed **disabled** in the spike; a real deployment sets a URL and a webhook secret (§13) |
| Never grant | `workflows`. Without it the bot cannot edit the check workflow, so it cannot remove its own gate |
| Installed on | `fq-sandbox` only (installation 184471304, "selected repositories") |
| Private key | `~/.secrets/fq-bot-dev-2.pem`, outside the repo; `*.pem`, `*.key`, `.secrets/` are gitignored |

## Ruleset layout

Two rulesets on the default branch, so the bypass covers review only.

- **A `review`:** require a PR with 1 approval, dismiss stale approvals, require approval of the last push. Bypass: the App, mode `pull_request`.
- **B `checks`:** require status check `fq-quarantine-check` from GitHub Actions (`integration_id` 15368). No bypass for anyone, including admins.

Exported from the API (`gh api repos/IrynaShkvirko/fq-sandbox/rulesets/<id>`, with `_links`, `node_id`, timestamps and `source` removed). Templates for new repos are in `spikes/github-app/rulesets.json`.

```json
{
  "id": 27810037,
  "name": "review",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "exclude": [], "include": ["~DEFAULT_BRANCH"] } },
  "rules": [
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "required_reviewers": [],
        "require_code_owner_review": false,
        "require_last_push_approval": true,
        "required_review_thread_resolution": false,
        "require_extra_approval_for_unattributed_changes": true,
        "allowed_merge_methods": ["merge", "squash", "rebase"]
      }
    }
  ],
  "bypass_actors": [{ "actor_id": 5866726, "actor_type": "Integration", "bypass_mode": "pull_request" }]
}
```

```json
{
  "id": 27809988,
  "name": "checks",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "exclude": [], "include": ["~DEFAULT_BRANCH"] } },
  "rules": [
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "do_not_enforce_on_create": false,
        "required_status_checks": [{ "context": "fq-quarantine-check", "integration_id": 15368 }]
      }
    }
  ],
  "bypass_actors": []
}
```

## Scenario results

All PRs are in `IrynaShkvirko/fq-sandbox`. Each scenario was run twice, with a separate PR per merge method:

- **Auto-merge:** GitHub's native auto-merge (GraphQL `enablePullRequestAutoMerge`, squash), on PRs #1–#5.
- **App merge:** `fq_bot.py --merge N` (REST `PUT /pulls/{n}/merge`, squash, pinned to the head SHA), on #1, #6, #7 and #8. These ran with GitHub's rulesets as the only guard, before the bot's own pre-merge verification was added (see [Security review](#security-review-pre-merge-verification)).

| # | Scenario | Expected | Auto-merge (PR) | App merge (PR) |
| --- | --- | --- | --- | --- |
| 1 | App PR changes only `quarantine.yaml` | check passes, merges with no review | ❌ #1: auto-merge on, check passed, but the PR stayed `BLOCKED` / `REVIEW_REQUIRED`. #3 behaved the same | ✅ #1: HTTP 200, merged by `app/fq-bot-dev-2` with no review |
| 2 | App PR also changes `README.md` (`--also-readme`) | check fails, no merge | ✅ #2: auto-merge on, check failed, not merged | ✅ #6: HTTP 405 "Required status check "fq-quarantine-check" is failing" |
| 3 | Human PR changes only `quarantine.yaml` | still needs a review | ✅ #4: auto-merge on, check passed, `BLOCKED` / `REVIEW_REQUIRED`, never merged | ✅ #8: owner's merge refused, HTTP 405 "New changes require approval from someone other than the last pusher" |
| 4 | App PR when the check fails (`--delete`: quarantine-only PR that deletes the file) | stays open | ✅ #5: auto-merge on, check failed, not merged | ✅ #7: HTTP 405 "Required status check "fq-quarantine-check" is failing" |
| extra | App pushes straight to `main` (contents API) | refused | — | ✅ HTTP 409 "Changes must be made through a pull request" |

The auto-merge PRs #2–#5 were closed afterwards so the App-merge runs could start from a clean `main`. #3 had been meant for scenario 4, but the `--delete` flag was not wired in yet, so it modified the file instead (an extra scenario-1 data point). #2, #4 and #5 conflicted once #1 merged; their auto-merge results above were read before they were closed.

The check itself was also run locally under GNU grep (the runner's grep) against 8 cases: modify and add pass; a second file, delete, symlink, exec bit, empty diff and rename-to-`quarantine.yaml` fail.

## Decision

**App-driven merge.** The bot opens the PR with no auto-merge, and merges it itself once `fq-quarantine-check` succeeds:

1. Trigger: a sweep job over open bot PRs with `bot_pull_requests.auto_merge` set. A `check_suite` `completed` webhook can run the same check sooner, if GitHub delivers it to the App for Actions-created suites (not verified: webhooks were off in the spike). Both paths are idempotent.
2. **Pre-merge verification by the bot**, independent of CI: bot author, same-repo branch, head SHA equal to the commit the bot pushed, exactly `quarantine.yaml` added or modified. See [Security review](#security-review-pre-merge-verification) for why this is required.
3. Merge: `PUT /repos/{repo}/pulls/{n}/merge` with `merge_method: squash` and `sha: <head sha>`, so a push after the check cannot be merged unchecked.
4. Ruleset B is a second layer: even if the bot calls merge too early or on a failing PR, GitHub refuses it (scenarios 2 and 4).
5. Over-cap PRs (§4.1 step 3.2) are simply never merged by the bot; the lead merges them by approving.

**Ruleset layout to require in user repos:** exactly the two rulesets above. A for review with the App as a `pull_request`-mode bypass actor; B for `fq-quarantine-check` pinned to GitHub Actions, with no bypass. Recommended for M3: set `allowed_merge_methods: ["squash"]` on ruleset A (not tested in the spike).

**Spec changes (agreed and made in `docs/architecture.md`, decision D39):**

- §2: new decision D39. "Auto-merge" in the spec means the bot merges its own PR through the REST API; GitHub's native auto-merge is not used.
- §9.5: the merge trigger (sweep, plus `check_suite` webhook), the bot's pre-merge verification, the merge call pinned to the head SHA, `checks: read` and the `check_suite` event, `workflows` never granted, the two-ruleset layout, and protecting release branches and tags.
- §4.1 step 3.3, §8.1 (API table: `check_suite` on the GitHub webhook), the §7 component diagram, the §8.4 sequence diagram, the `bot_pull_requests.head_sha` column (§10) and the `fq-bot-merge-sweep` CronJob (§14) updated to match.

## Security review: pre-merge verification

The security review of this PR found that the required check alone cannot keep the bypass limited to `quarantine.yaml`. A `pull_request` workflow runs the workflow file **from the PR head**, so anyone who can push to the bot's branch can rewrite the check. The App then merges whatever is there with no review.

Reproduced on `IrynaShkvirko/fq-sandbox-2`:

| Step | Result |
| --- | --- |
| Bot opens PR #3 (head `a643cd6`, only `quarantine.yaml`) | — |
| A human pushes a commit to the bot's branch that replaces the check with `echo` and changes `README.md` | **`fq-quarantine-check`: SUCCESS** on the new head `949e572`. GitHub's rulesets are satisfied: the App bypasses review and the check passed |
| `fq_bot.py --merge 3 --expect-sha a643cd6` (with the bot's own verification) | **refused by the bot:** 3 files changed, and the head is not the bot's commit. PR closed unmerged |

The bot's own checks, run live:

| Case | Result |
| --- | --- |
| fq-sandbox #6: `README.md` + `quarantine.yaml` | refused: not only `quarantine.yaml` |
| fq-sandbox #7: `quarantine.yaml` deleted | refused: status `removed` |
| fq-sandbox #8: human author | refused: author is not `fq-bot-dev-2[bot]` |
| fq-sandbox-2 #2: wrong `--expect-sha` | refused: head is not the bot's commit |
| fq-sandbox-2 #2: correct `--expect-sha` | HTTP 200, merged |

So the bot's pre-merge verification is the primary control, and the required check is a second layer. Both are now in §9.5.

## Setup for a new repo

**Measured:**

- `fq-sandbox` (first repo, by hand): about 3 minutes from the seed commit to both rulesets active, including creating and installing the App.
- `fq-sandbox-2` (second repo, `setup_repo.sh`): **5 min 38 s end to end**, from creating the repo to the App merging its smoke-test PR with no review (PR #1, check `SUCCESS`, merged by `app/fq-bot-dev-2`). 5 minutes of that was waiting for the one browser step (adding the repo to the App's installation). Everything else took 38 s.

To set up another repo, run steps 1–6 with one command; it pauses for the browser step:

```bash
FQ_APP_ID=… FQ_APP_KEY_PATH=… FQ_INSTALLATION_ID=… spikes/github-app/setup_repo.sh OWNER/REPO
```

The steps it automates:

1. **Repo:** public, or private on GitHub Pro / Team (rulesets on personal private repos need Pro). Squash merge allowed. "Allow auto-merge" is not needed.
2. **Seed `main`** (before any ruleset exists): `.github/workflows/fq-quarantine-check.yml` from `spikes/github-app/workflow/` and a `quarantine.yaml`.
3. **App:** first time only, `python3 spikes/github-app/create_app.py [--name fq-bot-dev]`, click **Create GitHub App**, and note the printed `FQ_APP_ID` / `FQ_APP_KEY_PATH`.
4. **Install** the App on the repo (first time: the printed install link, "Only select repositories"; later repos: Settings → Applications → the App → Configure → add the repo). This must happen **before** ruleset A: GitHub rejects a bypass actor that is not installed ("Actor … integration must be part of the ruleset source or owner organization").
5. **Rulesets**, from `spikes/github-app/rulesets.json`:

   ```bash
   jq --argjson id "$FQ_APP_ID" '.review | .bypass_actors[0].actor_id = $id' spikes/github-app/rulesets.json \
     | gh api -X POST repos/OWNER/REPO/rulesets --input -
   jq '.checks' spikes/github-app/rulesets.json | gh api -X POST repos/OWNER/REPO/rulesets --input -
   ```

6. **Smoke test:** `uv run spikes/github-app/fq_bot.py --repo OWNER/REPO --no-auto-merge` (prints the PR URL and `head:` SHA), wait for the check, then `uv run spikes/github-app/fq_bot.py --repo OWNER/REPO --merge <PR> --expect-sha <head>`. Expect HTTP 200.

## Open items

**Before closing M0-12 (#12):**

- [x] Run the four scenarios on `fq-sandbox` and fill in the results table.
- [x] Export both rulesets from the API and paste the JSON above.
- [x] Time the setup on a second repo (target: under 15 minutes): `fq-sandbox-2`, 5 min 38 s with `setup_repo.sh`.
- [x] Record the decision: App-driven merge, with the bot's own pre-merge verification. `fq_bot.py --merge` is the prototype; the sweep job and webhook handler are M3-01 work.
- [x] Security review: the bypass hole (a push to the bot's branch rewrites the check) was reproduced and closed by the pre-merge verification; §9.5 updated.
- [x] Agree the §9.5 / §4.1 changes above, including keeping `checks: read`: made in `docs/architecture.md` as D39.
- [x] Scenario 4: `fq_bot.py --delete` opens a quarantine-only PR whose check fails.

**Carry into M3-01 (the prototype is not production code):**

- [ ] `fq-bot-merge-sweep` job and `check_suite` handler that merge bot PRs: idempotent, pre-merge verification as in §9.5, merge pinned to `bot_pull_requests.head_sha`.
- [ ] Verify that GitHub delivers `check_suite` `completed` to the App for suites created by GitHub Actions. If not, use `workflow_run` or rely on the sweep alone.
- [ ] Try a ruleset on `refs/heads/fq/**` that blocks updates by anyone except the App (bypass mode `always`), so humans can't push to bot branches at all.
- [ ] Onboarding check: release branches and tags are protected by rulesets the App can't bypass (a leaked key with `contents:write` can push to anything unprotected).
- [ ] Pin `actions/checkout` and every other action by full commit SHA.
- [ ] Extend `fq-quarantine-check` with §9.5 content validation: schema, known tests or pending renames, no protected tests, a Jira key on every entry.
- [ ] Stale base: with `strict_required_status_checks_policy: false`, the check may have validated against an older `main`. §9.5 says the bot updates its branch and waits for the check again when `main`'s `quarantine.yaml` changed; implement that, or turn on strict mode.
- [ ] `put_file`: treat only 404 as "file missing"; raise on any other non-200. (`merge()` already exits non-zero on a refused merge.)
- [ ] Pin the httpx and pyjwt versions. Add bounded retries with backoff that respect 429 / `Retry-After` (CLAUDE.md).
- [ ] Never overwrite `quarantine.yaml` wholesale. Edit the entries instead.
- [ ] Validate repo names from the DB with the same `OWNER/NAME` pattern.

## Things to watch

- `fq-quarantine-check` is a **second layer**, not the guarantee: its workflow comes from the PR head. The spike check requires exactly one raw diff line, status `M`/`A`, mode `100644`, path `quarantine.yaml` (no deletes, renames or symlinks). M3 must add schema, protected-test and Jira-key validation (§9.5).
- The sandboxes are public, so forks can open PRs there. A public sandbox must never run the automatic merge path.
- Ruleset B pins the check to GitHub Actions (`integration_id` 15368) so nothing else can post a status with that name.
- Installation tokens are scoped to one repo with `contents` and `pull_requests` write only. Rotate the App key every 90 days (§9.5).
- `pull_request` bypass mode is what keeps the App off `main` directly: the direct push in the extra scenario was refused.
