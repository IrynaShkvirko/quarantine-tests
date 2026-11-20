# Commands

Slash commands for common workflows. Invoke with `/command-name` in Claude Code.

## Catalog

| Command | Description |
|---------|-------------|
| [/commit](commit.md) | Commit message in conventional format with the task ID, e.g. `feat(M1-01): ...` |
| [/create-branch](create-branch.md) | Branch named `<type>/<TASK-ID>/<description>`, e.g. `feat/M0-01/repo-skeleton` |
| [/create-pr](create-pr.md) | PR with file-specific description, change stats and `Closes #<issue>` |
| [/brainstorm](brainstorm.md) | Design session before building a new feature or architecture change |
| [/plan](plan.md) | Step-by-step implementation plan in `docs/plans/` |

## Shared Conventions

All Git commands follow the **git-workflow** skill (`.claude/skills/git-workflow/SKILL.md`):
- Conventional commit types; task ID (`M0-01`) as the scope
- Branch naming with the task ID
- PR description format with the issue link
- Never commit or push unless explicitly asked; run `make lint typecheck test` before pushing
