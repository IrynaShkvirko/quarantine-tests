#!/usr/bin/env bash
# Creates the M0 milestone, labels and the 13 M0 issues from docs/tasks/M0/*.md.
# Safe to run again: existing issues (matched by their "[M0-xx]" title prefix) are updated, not duplicated.
# M0-03's import script later takes over these issues and creates M1–M7.
#
# Usage: scripts/github/create_m0_issues.sh [owner/repo] [--dry-run]
# Repo default: $FQ_GITHUB_REPO, else the repo of the current directory.
# Needs: gh (logged in with `gh auth login`, scope `repo`). Works with macOS bash 3.2.
set -euo pipefail

REPO="${1:-${FQ_GITHUB_REPO:-}}"
DRY_RUN=false
[[ "${2:-}" == "--dry-run" || "${1:-}" == "--dry-run" ]] && DRY_RUN=true
[[ "$REPO" == "--dry-run" ]] && REPO="${FQ_GITHUB_REPO:-}"
[[ -n "$REPO" ]] || REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="$ROOT/docs/tasks/M0"
MILESTONE="M0"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

run() { if $DRY_RUN; then echo "DRY-RUN: $*"; else "$@"; fi; }

command -v gh >/dev/null || { echo "gh CLI not found: https://cli.github.com" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Run 'gh auth login' first" >&2; exit 1; }

echo "Repository: $REPO"

# 1. Milestone
if gh api "repos/$REPO/milestones?state=all&per_page=100" --jq '.[].title' | grep -qx "$MILESTONE"; then
  echo "Milestone $MILESTONE exists"
else
  run gh api "repos/$REPO/milestones" -f title="$MILESTONE" \
    -f description="Foundations + risk spikes: repo, local env, CI, config schemas, ingestion contract, DB schema, docs site, 3 spikes" >/dev/null
  echo "Created milestone $MILESTONE"
fi

# 2. Labels (name:color:description); --force updates existing ones
labels=(
  "milestone:M0:5319e7:Milestone M0 — Foundations + risk spikes"
  "infra:0e8a16:Repo, CI, environment, deployment"
  "backend:1d76db:Python backend"
  "ci:fbca04:CI adapters and fq-cli"
  "plugins:c5def5:pytest / Playwright / Jest reporters"
  "integrations:d4c5f9:GitHub, Jira, Slack clients"
  "docs:0075ca:Documentation and docs site"
  "spike:e99695:Timeboxed investigation"
)
for entry in "${labels[@]}"; do
  # label names may contain ':' (milestone:M0) — split from the right
  desc="${entry##*:}"; tmp="${entry%:*}"; color="${tmp##*:}"; name="${tmp%:*}"
  run gh label create "$name" --repo "$REPO" --color "$color" --description "$desc" --force >/dev/null
done
echo "Labels ready"

# 3. Issues (first pass: create or update, without dependency links)
find_issue() {  # $1 = task id → issue number or empty
  gh issue list --repo "$REPO" --state all --limit 200 --search "\"[$1]\" in:title" \
    --json number,title --jq ".[] | select(.title | startswith(\"[$1]\")) | .number" | head -n1
}
body_of() {  # $1 = file, $2 = depends text → writes body to $TMP/body.md
  awk 'f{print} /^---$/ && !f {f=1}' "$1" | sed "s|{{DEPENDS}}|$2|" > "$TMP/body.md"
}

for file in "$DIR"/M0-*.md; do
  id="$(basename "$file" .md)"
  title="$(sed -n 's/^title: //p' "$file" | head -n1)"
  labels_csv="$(sed -n 's/^labels: //p' "$file" | head -n1)"
  body_of "$file" "see below"
  existing="$(find_issue "$id")"
  if [[ -n "$existing" ]]; then
    run gh issue edit "$existing" --repo "$REPO" --title "$title" --body-file "$TMP/body.md" \
      --add-label "$labels_csv" --milestone "$MILESTONE" >/dev/null
    echo "$existing" > "$TMP/num_$id"; echo "Updated #$existing $title"
  else
    if $DRY_RUN; then
      echo "DRY-RUN: create '$title' [$labels_csv]"; echo "?" > "$TMP/num_$id"
    else
      url="$(gh issue create --repo "$REPO" --title "$title" --body-file "$TMP/body.md" \
        --label "$labels_csv" --milestone "$MILESTONE")"
      echo "${url##*/}" > "$TMP/num_$id"; echo "Created #${url##*/} $title"
    fi
  fi
done

# 4. Second pass: dependency links now that every issue has a number
for file in "$DIR"/M0-*.md; do
  id="$(basename "$file" .md)"
  deps="$(sed -n 's/^depends: //p' "$file" | head -n1)"
  if [[ -z "$deps" ]]; then
    text="none"
  else
    text=""
    for d in $deps; do text="${text:+$text, }#$(cat "$TMP/num_$d") ($d)"; done
  fi
  grep -q '{{DEPENDS}}' "$file" || continue
  body_of "$file" "$text"
  run gh issue edit "$(cat "$TMP/num_$id")" --repo "$REPO" --body-file "$TMP/body.md" >/dev/null
done
echo "Dependency links set"

echo
echo "Done. Next: add the issues to a Project board (M0-03 automates this), then start Wave 1:"
echo "  M0-01 (repo skeleton) + spikes M0-10, M0-11, M0-12 + contract draft M0-08."
