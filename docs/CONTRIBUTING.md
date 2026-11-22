# Contributing

How work gets from an issue to `main`. Rules for code and tests are in [`CLAUDE.md`](../CLAUDE.md); the longer versions are in `.claude/skills/git-workflow/SKILL.md`.

## One issue, one branch, one PR

1. Pick one issue (`[M0-01] ...`). Read its acceptance criteria and the spec sections it cites.
2. Create a branch from `main`.
3. Open one PR per issue, filled in from the PR template. The body ends with `Closes #<issue>`.

## Branch names

`<type>/<task-id>/<kebab-description>`, for example `feat/M0-01/repo-skeleton`.

- Types: `feat`, `fix`, `improvement`, `refactor`, `chore`, `docs`, `test`.
- CI, tooling and build work uses `chore` (there is no `ci` branch type), for example `chore/M0-04/project-ci`.
- Work without a task ID: `<type>/<kebab-description>`, for example `docs/update-architecture-section-9`.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) with the task ID as scope:

```text
<type>(<task-id>): <short description>
feat(M1-01): add ingestion endpoint with repo token auth
```

- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`.
- Imperative mood, under 72 characters, no trailing period, one line.
- The PR title uses the same format.

## Merging

PRs are squash-merged, so the PR title becomes the commit on `main`. Keep history linear and delete the branch after the merge.

## Before you push

```bash
make lint typecheck test
```

CI runs the same commands, so a local failure fails the PR. Run `pytest -m integration` too when you touch the database, queue or migrations (needs `make up`, from M0-05).

## Issues

Open issues from the **Task** or **Spike** form. A task that needs more than about a day gets a plan in `docs/plans/` first.

## Project CI

`.github/workflows/project-ci.yml` runs on every pull request and on pushes to `main`. Newer runs on the same branch cancel older ones (never on `main`).

| Job | Runs when | What it does |
| --- | --- | --- |
| `changes` | always | `dorny/paths-filter` decides which jobs below run |
| `python` | Python, lockfile or workflow changes | `uv sync --frozen`, `make lint`, `make typecheck`, pytest with coverage for `backend`, `plugins/pytest-flaky-reporter`, `ci/fq-cli`; uploads `coverage.xml` |
| `node` | TypeScript, lockfile or workflow changes | `pnpm install --frozen-lockfile`, `pnpm lint` (eslint + prettier), `pnpm -r typecheck`, `pnpm -r test` |
| `integration` | same as `python` | Postgres 16 service, `alembic upgrade head`, `pytest -m integration`. Skipped until M0-06 adds `backend/alembic.ini`; passes with no integration tests collected until then |
| `docker` | backend or lockfile changes | Builds `backend/Dockerfile` with the BuildKit cache, no push. Skipped until M0-05 adds the Dockerfile |
| `pre-commit` | PR changes any non-docs file | `pre-commit run --all-files`, so local hooks can't be skipped with `--no-verify` |
| `docs-only` | PR changes only documentation (`docs/**`, `docs-site/content/**`, root `README.md`) | Fast path: the docs-relevant pre-commit hooks (end-of-file, trailing whitespace, YAML, private keys) on all files |
| `ci-ok` | always | Fails if any job above failed or was cancelled. Path-filtered jobs may be skipped. `changes` never is, and exactly one of `pre-commit` (code PRs) or `docs-only` (docs PRs) runs |

The `docs` workflow (Fumadocs build and Pages deploy) is **not** a required check.

All actions are pinned by full commit SHA with the version in a comment. Dependabot (`.github/dependabot.yml`) bumps `uv`, `npm` and `github-actions` weekly, grouping minor and patch updates.

## Branch protection on `main`

Create a repository ruleset (Settings → Rules → Rulesets → New branch ruleset), or send the JSON below with
`gh api -X POST repos/OWNER/REPO/rulesets --input ruleset.json`.

Settings:

- Target: default branch, enforcement **Active**.
- Require a pull request before merging.
- Require status checks to pass: **exactly `ci-ok` and `docs-only`**, both pinned to the GitHub Actions app (`integration_id` 15368) so a commit status posted by anything else can't satisfy them. Do not add `docs` or any other job.
- Require linear history.
- Block force pushes (and branch deletion).

The check names come from the job names in `project-ci.yml`. `docs-only` is skipped on code PRs, and GitHub treats a skipped required job as passing.

```json
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [],
  "rules": [
    { "type": "pull_request", "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false } },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [ { "context": "ci-ok", "integration_id": 15368 }, { "context": "docs-only", "integration_id": 15368 } ] } },
    { "type": "required_linear_history" },
    { "type": "non_fast_forward" },
    { "type": "deletion" }
  ]
}
```

Applying this ruleset is a repository-admin action and is not done by CI. The App rulesets for target repos (spike M0-12) are separate.
