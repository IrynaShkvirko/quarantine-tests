# Git Workflow — Examples

Task IDs come from the implementation plan and the GitHub issue titles (`[M1-01] Ingestion endpoint`).

## Commit Messages

### Good

```
feat(M1-01): add ingestion endpoint with repo token auth
```

```
fix(M2-06): ignore cross-run evidence from environmental runs
```

```
refactor(M3-07): move PR batching into quarantine manager
```

```
test(M2-07): cover window selection at the 30-execution boundary
```

```
ci(M0-04): add path filters so docs-only PRs skip python jobs
```

```
chore: bump sqlalchemy to the latest 2.0 patch release
```

### Bad

```
feat(M1-01): added ingestion endpoint          ← past tense
feat(M1-01): add ingestion endpoint.           ← trailing period
fix(M2-06): fix bug                            ← says nothing
feat: add endpoint, masking, status route, tests and docs   ← several changes in one commit
feat(m1-01): add ingestion endpoint            ← task ID must be uppercase
```

## Pull Requests

### Feature PR

**Title:** `feat(M1-01): add ingestion endpoint with repo token auth`

```markdown
## What was done

- Added `POST /api/v1/ingest/runs` in `backend/app/api/ingest.py` (multipart: metadata + JUnit files)
- Added repo token check as a FastAPI dependency in `backend/app/api/deps.py` (hashed, constant-time)
- Added idempotency on the ingestion key in `backend/app/db/repositories/uploads.py`
- Added `GET /api/v1/ingest/runs/{upload_id}` status route

**Logic:** +312 −8 | **Tests:** +240 −0

## Tests

`backend/tests/integration/api/test_ingest.py` (7 tests):
- 202 on valid upload, 400 on schema error, 401 on bad token, 413 on oversized upload
- Duplicate upload returns the first `upload_id` and stores one row

## Task

M1-01 · Closes #14
```

### Fix PR with alternatives

**Title:** `fix(M2-06): ignore cross-run evidence from environmental runs`

```markdown
## What was done

- Excluded runs with `is_environmental = true` from the cross-run lookup in `backend/app/db/repositories/evidence.py`
- Added the environmental flag to the rerun-evidence path in `backend/app/domain/detector.py`

**Logic:** +24 −6 | **Tests:** +58 −0

**Why filter at query time over deleting evidence:**

- **Delete flaky_events after the run is flagged** — loses history needed for the environmental-run alert
- **Filter in Python after loading** — loads far more rows than needed
- **Filter in the evidence query** — one indexed condition, history kept

## Tests

`backend/tests/unit/domain/test_detector.py` (2 tests):
- Rerun evidence from an environmental run is not counted
- Cross-run evidence pairing with an environmental run is not counted

## Task

M2-06 · Closes #41
```

## Branch Names

```
feat/M0-01/repo-skeleton
feat/M1-01/ingestion-endpoint
fix/M2-06/environmental-runs
test/M2-07/window-boundaries
ci/M0-04/path-filters
docs/architecture-section-9
chore/bump-sqlalchemy
```

## A Task Across Several Commits

Branch: `feat/M1-01/ingestion-endpoint`

```
feat(M1-01): add ingestion request and metadata models
feat(M1-01): add repo token dependency
feat(M1-01): add ingestion route and idempotent raw upload storage
test(M1-01): cover 400/401/413 and duplicate upload
```

PR title: `feat(M1-01): add ingestion endpoint with repo token auth` — squash-merged into one commit on `main`.
