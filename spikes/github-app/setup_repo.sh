#!/usr/bin/env bash
# M0-12 spike: set up the fq bot on one more repo and smoke-test it, timed.
#
#   FQ_APP_ID=... FQ_APP_KEY_PATH=... FQ_INSTALLATION_ID=... \
#     spikes/github-app/setup_repo.sh OWNER/REPO
#
# Needs: gh (logged in as the repo owner, scopes repo + workflow), git, jq, uv.
# The App itself must already exist (create_app.py) and be installed on the account.
set -euo pipefail

repo="${1:?usage: setup_repo.sh OWNER/REPO}"
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "repo must be OWNER/NAME" >&2; exit 2; }
: "${FQ_APP_ID:?}" "${FQ_APP_KEY_PATH:?}" "${FQ_INSTALLATION_ID:?}"
here="$(cd "$(dirname "$0")" && pwd)"
start=$(date +%s)
step() { printf '[%3ss] %s\n' "$(( $(date +%s) - start ))" "$*"; }

# 1. Repo: public, because rulesets on personal private repos need GitHub Pro.
if ! gh repo view "$repo" >/dev/null 2>&1; then
  gh repo create "$repo" --public --description "fq bot sandbox" >/dev/null
fi
gh api -X PATCH "repos/$repo" -F allow_squash_merge=true >/dev/null
step "repo ready: $repo"

# 2. Seed main before any ruleset exists.
seed="$(mktemp -d)"
trap 'rm -rf "$seed"' EXIT
mkdir -p "$seed/.github/workflows"
cp "$here/workflow/fq-quarantine-check.yml" "$seed/.github/workflows/"
printf '# Tests excluded from the blocking CI job\ntests: []\n' > "$seed/quarantine.yaml"
printf '# %s\n\nfq bot sandbox.\n' "${repo#*/}" > "$seed/README.md"
git -C "$seed" init -q -b main
git -C "$seed" add .
git -C "$seed" commit -q -m "chore: seed fq bot sandbox"
git -C "$seed" push -q "https://github.com/$repo.git" main
step "main seeded"

# 3. Add the repo to the App's installation (browser fallback if the token can't).
repo_id="$(gh api "repos/$repo" -q .id)"
if gh api -X PUT "user/installations/$FQ_INSTALLATION_ID/repositories/$repo_id" >/dev/null 2>&1; then
  step "repo added to installation $FQ_INSTALLATION_ID via API"
else
  step "add $repo to the App in the browser: Settings > Applications > the App > Configure"
fi

# 4. Rulesets. 'checks' first; 'review' fails until the App is installed on the repo, so retry.
jq '.checks' "$here/rulesets.json" | gh api -X POST "repos/$repo/rulesets" --input - >/dev/null
step "ruleset 'checks' active"
review="$(jq --argjson id "$FQ_APP_ID" '.review | .bypass_actors[0].actor_id = $id' "$here/rulesets.json")"
for _ in $(seq 1 120); do
  if printf '%s' "$review" | gh api -X POST "repos/$repo/rulesets" --input - >/dev/null 2>&1; then break; fi
  sleep 5
done
gh api "repos/$repo/rulesets" -q '.[].name' | grep -qx review || { echo "ruleset 'review' not created" >&2; exit 1; }
step "ruleset 'review' active (App bypass)"

# 5. Smoke test: bot PR -> check passes -> App merges with no review.
pr="$(uv run -q "$here/fq_bot.py" --repo "$repo" --no-auto-merge | sed -n 's#.*/pull/##p')"
step "bot PR #$pr opened"
for _ in $(seq 1 60); do
  state="$(gh pr view "$pr" -R "$repo" --json statusCheckRollup -q '[.statusCheckRollup[].conclusion] | join(",")')"
  [[ -n "$state" ]] && break
  sleep 5
done
[[ "$state" == "SUCCESS" ]] || { echo "check did not pass: '$state'" >&2; exit 1; }
uv run -q "$here/fq_bot.py" --repo "$repo" --merge "$pr"
step "done: PR #$pr merged by the App. Total $(( $(date +%s) - start ))s"
