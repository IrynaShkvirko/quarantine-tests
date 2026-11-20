# Skills

Reusable knowledge and workflows that agents load on demand. Each skill is a folder with a `SKILL.md` (required) and optional `examples.md` / `references.md`. The project design lives in `docs/architecture.md`; skills say how to build it well.

## Catalog

| Skill | Area | Use it for |
|-------|------|------------|
| [backend-best-practices](backend-best-practices/SKILL.md) | `backend/`, `ci/fq-cli/` | Layers, FastAPI, SQLAlchemy/Alembic, Procrastinate tasks, integration clients, logging |
| [backend-testing](backend-testing/SKILL.md) | Python | pytest, golden files, hypothesis, transactional Postgres fixtures, fakes, determinism rules |
| [security](security/SKILL.md) | All | Threat model, ingestion/webhook/parsing rules, credentials, Actions/Jenkins hardening |
| [git-workflow](git-workflow/SKILL.md) | All | Conventional commits with task IDs (`M0-01`), branch names, PR format, push checks |
| [writing-plans](writing-plans/SKILL.md) | All | Step-by-step plans for issues bigger than ~1 day |
| [brainstorming](brainstorming/SKILL.md) | All | Design before code for new features or architecture changes |
| [systematic-debugging](systematic-debugging/SKILL.md) | All | Root-cause debugging, including flaky-detection and webhook issues |
| [mermaid-diagram](mermaid-diagram/SKILL.md) | Docs | Diagrams for `docs/` (the architecture uses Mermaid) |
| [react-best-practices](react-best-practices/SKILL.md) | `ui/` (M7) | React component and hook patterns for the custom UI |
| [react-testing-library](react-testing-library/SKILL.md) | `ui/` (M7) | Testing the custom UI with RTL and Vitest |

## Skills vs Agents vs Commands

| Type | Location | Loaded | Purpose |
|------|----------|--------|---------|
| Project rules | `CLAUDE.md` | Always | Commands, layout rules, definition of done |
| Skills | `.claude/skills/` | On demand, or via an agent's `skills:` list | Domain knowledge |
| Agents | `.claude/agents/` | Via the Task tool | Focused workflows (implement, test, review, plan) |
| Commands | `.claude/commands/` | `/command` | Repeatable user actions (commit, branch, PR, plan) |

## Adding a Skill

- `SKILL.md` with frontmatter `name` and a `description` that says **when** to use it
- Keep rules specific to this project's stack and architecture; link sections of `docs/architecture.md` instead of repeating them
- Add it to the catalog above and to the `skills:` list of any agent that should load it
