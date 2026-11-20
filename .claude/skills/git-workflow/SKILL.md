---
name: git-workflow
description: "Git workflow conventions for branches, commits, and PRs. Use when creating branches, generating commit messages, creating pull requests, or any Git operation that needs to follow project conventions. Covers conventional commits, branch naming with task IDs (M0-01), PR formatting with issue links, and pre-push checks (make lint typecheck test)."
---

# Git Workflow

Conventions for Git operations in this project. The "ticket" is the task ID from the implementation plan (`M0-01`, `M3-07`), which is also in the GitHub issue title (`[M0-01] Repo skeleton and tooling`).

For complete examples of commits, PRs, and branches, see [examples.md](references/examples.md).

## CRITICAL: Commit & Push Policy

- **NEVER commit or push unless the user EXPLICITLY and DIRECTLY asks for it**
- **ONE commit or push per explicit request** — do not batch, retry, or repeat
- After making code changes, WAIT for the user to say "commit" or "push"
- This applies in ALL scenarios: bug fixes, PR review comments, feature work, refactors
- If a commit fails (e.g., pre-commit hook), fix the issue and WAIT for the user to ask again
- NEVER auto-commit as part of completing a task

## Conventional Commit Types

| Type | Use for |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, semicolons, etc. |
| `refactor` | No feature/fix, code restructuring |
| `perf` | Performance improvements |
| `test` | Adding or updating tests |
| `chore` | Maintenance, dependencies |
| `ci` | CI/CD changes |
| `build` | Build system changes |

## Message Format

All commits, PR titles, and related messages use:

```
<type>(<TICKET>): <short description>
```

- Task ID in scope is **required** when available (e.g., `M0-01`)
- Scope must match: `M\d+-\d{2}`
- Description: imperative mood, under 72 chars, no trailing period
- Keep to 1 line (2 max) — no bullet-point lists in commit messages

Examples:
- `feat(M1-01): add ingestion endpoint with repo token auth`
- `fix(M2-06): ignore cross-run evidence from environmental runs`
- `refactor(M3-07): move PR batching into quarantine manager`

## Branch Naming

**With task ID:** `<type>/<TASK-ID>/<kebab-description>`
**Without task ID:** `<type>/<kebab-description>`

Branch types: `feature`, `feat`, `fix`, `improvement`, `refactor`, `chore`, `docs`, `test`

Examples:
- `feat/M0-01/repo-skeleton`
- `fix/M2-06/environmental-runs`
- `docs/update-architecture-section-9`

## Task ID Extraction

Extract the task ID from the branch name:

```bash
git branch --show-current
# e.g., "feat/M0-01/repo-skeleton" → task ID is "M0-01"
```

Find the matching GitHub issue number with `gh issue list --search "[M0-01] in:title" --json number`. If there is no task ID in the branch name, ask the user.

## PR Description Format

Every PR description follows this structure. Sections marked *(conditional)* are only included when applicable.

```markdown
## What was done

- <Action verb> <specific change> in `<filename>`
- <Action verb> <specific change>

**Logic:** +<src_ins> −<src_del> | **Tests:** +<test_ins> −<test_del>

**Why `<approach>` over alternatives:** *(optional — only if complex, ASK the user first)*

- **<Alternative 1>** — why it doesn't work or was rejected
- **<Alternative 2>** — why it doesn't work or was rejected
- **<Chosen approach>** — why this was selected, how it works

## Tests *(conditional — only if PR includes test changes)*

`<test_file.py>` (N tests):
- <What the tests cover>
- <Key scenarios tested>

`<another.test.ts>` (N tests):
- <What the tests cover>

## Task

M<n>-<nn> · Closes #<issue number>
```

### Section Rules

**What was done:**
- Be file-specific — mention actual file/component names
- Start with action verbs: Added, Removed, Fixed, Updated, Refactored, Created
- One change per bullet, max 5-7 bullets
- Use backticks for file names and code references

**Why (alternatives) section:**
- Include ONLY when the PR involves a non-trivial design decision
- Before writing this section, **ASK the user** whether they want to document alternatives and the reasoning
- List rejected approaches with short explanations of why they don't apply
- End with the chosen approach and its benefits
- Use bold for approach names, em-dash for explanations

**Tests section:**
- Include when the PR adds or modifies test files
- List each test file with the number of tests in parentheses
- Under each file, summarize what's tested (not individual test names)

**Task section:**
- Always include the task ID from the branch name and `Closes #<issue>` so merging closes the GitHub issue
- List acceptance criteria that are NOT fully met, if any (should be none)

### Change Stats

When creating the PR, compute line-level change stats split by source vs test code:

```bash
# Total stats
git diff main...HEAD --stat | tail -1

# Test file stats (test_*.py, *_test.py, *.test.ts, golden fixtures)
git diff main...HEAD -- '**/test_*.py' '**/*_test.py' '**/*.test.ts' '**/tests/fixtures/**' '**/tests/golden/**' --stat | tail -1

# Source = total minus test
```

Include a summary line after "What was done" bullets:

```markdown
**Logic:** +280 −78 | **Tests:** +67 −11
```

- **Logic** = lines changed in non-test files (features, fixes, refactors)
- **Tests** = lines changed in test files and test fixtures
- If no test files changed, show only Logic: `**Logic:** +347 −89`

## GitHub Operations

- Use the `gh` CLI for GitHub operations (PRs, issues, project board); use GitHub MCP tools instead if they're available in the session
- Add the PR to the "Flaky Test Quarantine" project board and set Status to Review

## Push Policy

- **NEVER push changes unless the user explicitly asks to push**
- Before pushing, always ask the user for confirmation first
- If the user asks to push, run the checks first:

```bash
make lint && make typecheck && make test
# plus, when DB, queue or migrations changed (needs `make up`):
pytest -m integration
# plus, when TypeScript plugins changed:
pnpm -r lint && pnpm -r typecheck && pnpm -r test
```

Only push if all checks pass. CI runs the same commands, so a local failure will fail the PR.
