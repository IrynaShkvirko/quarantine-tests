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
