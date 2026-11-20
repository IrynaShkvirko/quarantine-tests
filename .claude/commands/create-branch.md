# create-branch

Create a new Git branch following the project's naming conventions.

## Prerequisites

Read the git-workflow skill at `.claude/skills/git-workflow/SKILL.md` for branch naming conventions and types.

## Input Parameters

- **Type**: {{type}} (e.g., feature, fix, improvement, docs)
- **Task ID**: {{ticket}} (e.g., M0-01, from the GitHub issue title; leave empty if none)
- **Description**: {{description}} (brief kebab-case description)

## Instructions

1. Convert description to kebab-case (lowercase, hyphens)
2. Keep description concise (max 30 characters recommended)
3. Task ID is uppercase `M` + milestone + `-` + two digits (e.g., `M0-01`)
4. For bug fixes with tickets, use `fix` (not `bug`)
5. If no task ID provided, omit that segment
6. Example: `feat/M0-01/repo-skeleton`

## Command

```bash
git checkout -b <generated-branch-name>
```

## Output

Confirm:
- Branch name created
- Current branch status
- Ready for development
