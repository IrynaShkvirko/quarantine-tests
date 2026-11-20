---
name: systematic-debugging
description: "Use when investigating bugs, errors, or unexpected behavior. Activates when something is broken and needs diagnosis. Enforces root-cause analysis before any fix attempt."
---

# Systematic Debugging

A structured approach to finding and fixing bugs. No guessing, no random changes.

## Core Rule

**No fixes without root cause first.** If you can't explain WHY the bug happens, you don't understand it well enough to fix it.

> **Tip:** For timing or concurrency bugs (worker races, out-of-order webhooks), add structured log lines with `upload_id` / `test_id` and replay the scenario in a test with fakes before touching the code.

## When This Activates

- Something is broken or behaving unexpectedly
- Tests are failing
- An error appears in the console, logs, or UI
- The user reports a bug
- A fix attempt hasn't worked

## Phase 1: Gather Evidence

Before forming any hypothesis, collect facts:

### Read Error Messages
- Read the FULL error message, including stack traces
- Identify the exact file and line number
- Note the error type (TypeError, SyntaxError, 404, 500, etc.)

### Reproduce the Bug
- Find the exact steps to reproduce
- Note: does it happen every time or intermittently?
- Note: does it happen in dev, production, or both?

### Check Recent Changes
```bash
git log --oneline -10
git diff HEAD~1
```
- What changed recently? Did this work before?
- Did a dependency update break something?

### Read Relevant Code
- Read the file where the error occurs
- Read the callers (what invokes this code?)
- Read the dependencies (what does this code depend on?)

### Check Logs
- Browser console and network tab (UI only, M7)
- API and worker logs (`make logs`, JSON lines with `request_id`, `upload_id`, `test_id`)
- Database state (`make psql`) and Procrastinate job table (failed / retried jobs)
- The raw upload and its parse status (`GET /api/v1/ingest/runs/{upload_id}`)
- CI job logs and the uploaded JUnit artifact

## Phase 2: Analyze Patterns

Look for patterns in the evidence:

- **When** does it fail? (Always? Only on certain input? Only after another action?)
- **Where** does it fail? (CI adapter / plugin? Ingestion? Parsing? Detection? Worker? External service? Database?)
- **What** changed? (Code? Data? Environment? Dependencies?)
- **Who** is affected? (One repo? One framework? One CI system? One team's tests?)

### Common Patterns

| Pattern | Likely Cause |
|---------|-------------|
| Works locally, fails in production | Environment variable or build config issue |
| Same JUnit parsed differently by framework | Normalizer or plugin doesn't follow the contract in `docs/contracts/` |
| Intermittent failures | Race condition, timing, or network issue |
| Works for some data, fails for others | Data validation or edge case |
| Error after dependency update | Breaking API change in dependency |
| 401/403 on ingestion | Wrong or rotated repo token, or metadata repository doesn't match the token |
| Webhook ignored | Signature check failed (secret mismatch) or delivery already processed |
| Test quarantined unexpectedly | Check flaky_events evidence, environmental-run flag, window size and the policy decision record |
| Duplicate PR / ticket / Slack message | Task not idempotent, or ran twice after a retry |
| Passes alone, fails in the suite | Order dependence — reproduce with `pytest -p randomly -p "randomly_seed=<seed>"` |
| Postgres connection errors | `make up` not running or `FQ_DATABASE_URL` wrong |

## Phase 3: Form and Test Hypotheses

Based on evidence, form a specific hypothesis:

**Template:** "The bug occurs because [specific cause] which results in [observed behavior] when [trigger condition]."

### Test the Hypothesis

- Add targeted logging/instrumentation to verify
- Check if the hypothesis explains ALL observed symptoms
- If the hypothesis is wrong, go back to Phase 1 and gather more evidence

### Rules for Hypothesis Testing

1. **One change at a time.** Never change multiple things simultaneously.
2. **Verify before AND after.** Confirm the bug exists, then confirm the fix works.
3. **Check side effects.** Does the fix break anything else?
4. **Understand, don't guess.** If you can't explain why the fix works, you haven't found the root cause.

## Phase 4: Fix and Verify

### Implement the Fix

1. Make the minimal change that fixes the root cause
2. Don't fix symptoms — fix the cause
3. Add defensive code if appropriate (input validation, null checks)
4. Consider: should we add a test that catches this regression?

### Verify the Fix

- [ ] The original bug no longer reproduces
- [ ] No new errors in console/logs
- [ ] Related functionality still works (manual test or run tests)
- [ ] Edge cases are handled

### Document the Fix

In your commit message or PR description, include:
- What was broken
- What caused it (root cause)
- What was changed to fix it

## Escalation Rules

### After 3 Failed Fix Attempts

Stop and reassess:

1. Am I solving the right problem?
2. Is my understanding of the system correct?
3. Should I read more code or logs?
4. Is this an architecture issue, not a bug?
5. Should I ask the user for more context?

### When to Step Back

- If you've been debugging for more than 15 minutes without progress
- If the fix keeps breaking something else
- If you can't reproduce the bug consistently
- If the code path is too complex to reason about

In these cases: simplify, add logging, and gather more evidence.

## Anti-Patterns

- **Shotgun debugging:** Making random changes hoping one works
- **Cargo cult fixes:** Copying a fix from Stack Overflow without understanding it
- **Symptom fixing:** Adding a null check instead of finding why it's null
- **Silent swallowing:** Wrapping in try-catch with empty catch block
- **"Works on my machine":** Dismissing the bug because you can't reproduce it locally

## Remember

- Bugs are information — they tell you something about the system you didn't know
- The fix should be proportional to the bug — a one-line bug usually has a one-line fix
- If the fix is complex, question whether you've found the real root cause
- Always verify the fix. "It should work" is not verification.
