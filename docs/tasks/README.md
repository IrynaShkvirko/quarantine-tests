# Task import

Tasks live in GitHub Issues, milestones and the "Flaky Test Quarantine" project board. `scripts/github/import_tasks.py` creates and updates all of them from the Implementation Plan sheet, so nobody edits 76 issues by hand. It is safe to run again after the plan changes. GitHub is the source of truth for status once issues exist; nothing is synced back to the sheet.

## Flow

1. **Export.** In the Implementation Plan sheet, `File → Download → CSV` for the Tasks tab. Columns: `ID, Milestone, Task, Component, Est. days, Depends on, Status, Doc §, Scope, Acceptance criteria`. Optionally export the Milestones tab as a CSV with `Milestone, Description` columns.
2. **Split (optional).** Export the breakdown doc as Markdown and split it on the `## M0-` headings into one file per task in `docs/tasks/` (`M0-01.md`, …). A task with a body file uses it; otherwise the body is built from the CSV's Scope and Acceptance criteria. A file may start with a `title / labels / depends` header ended by `---`; the header is dropped. `{{DEPENDS}}` is replaced by the issue links.
3. **Import.** Look first, then write:

   ```bash
   gh auth login   # scopes: repo, project
   python scripts/github/import_tasks.py --tasks tasks.csv --bodies docs/tasks/ \
     --repo IrynaShkvirko/quarantine-tests --dry-run
   python scripts/github/import_tasks.py --tasks tasks.csv --bodies docs/tasks/ \
     --repo IrynaShkvirko/quarantine-tests
   ```

   Add `--milestones milestones.csv` to set milestone descriptions.

## What it does

- Creates milestones, labels (`milestone:Mx`, one per component, `spike`, `later`) and the project with a Status field (To do / In progress / Review / Done) and an Estimate field.
- Finds each issue by the marker `<!-- fq-task-id: M0-01 -->` at the end of its body, falling back to the `[M0-01]` title prefix, so the 13 issues made by `create_m0_issues.sh` are adopted, not duplicated. Two issues with the same marker stop the run.
- Updates title, body, labels and milestone only when they differ. Labels are only added, except `later`, which is removed when a task is scheduled again.
- Tasks with Status `Later` get the `later` label and no milestone; they stay open.
- Writes "Depends on" links into each body after all issues exist, and also sets GitHub's native "blocked by" links. If the API refuses, a warning is printed and the body list stays.
- Adds every issue to the board with its estimate. Existing Status values on the board are never changed.
- Prints a table of create / update / skip rows; a second run with no plan changes prints `no changes`. `--dry-run` only reads from GitHub.
