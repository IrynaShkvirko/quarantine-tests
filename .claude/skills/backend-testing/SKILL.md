---
name: backend-testing
description: "Testing conventions for the flaky test quarantine system's Python code — pytest, pytest-asyncio, hypothesis, golden files, transactional Postgres fixtures, httpx ASGI client, fakes for GitHub/Jira/Slack, and rules that keep our own tests deterministic. Use when writing, reviewing or planning tests under backend/, ci/fq-cli/ or plugins/pytest-flaky-reporter/."
---

# Backend Testing

This system judges other teams' tests as flaky. Its own tests must be beyond reproach: deterministic, fast, and meaningful.

## Philosophy

1. **Use-case coverage over line coverage.** Each acceptance criterion and each failure mode has a test.
2. **Pure core, many small tests.** `app/domain/` gets exhaustive table-driven tests; they run in milliseconds.
3. **Thin edges, fewer bigger tests.** Routes, tasks and repositories get integration tests through real Postgres.
4. **Mock at the boundary only.** Replace GitHub, Jira and Slack with fakes. Never mock our own DB, domain or repositories.
5. **Every test must be able to fail.** If breaking the feature wouldn't break the test, the test is wrong.

## The Test Pyramid for This Repo

| Level | What | Tools | Share |
|-------|------|-------|-------|
| Unit | `domain/`, `config/`, parsers, masking, fq-cli helpers | pytest, parametrize, hypothesis, golden files | Most |
| Integration | API routes, repositories, migrations, tasks, cron jobs | pytest + Postgres (`fq_test`), httpx ASGI client, Procrastinate | Some |
| End-to-end | One flow per milestone: upload → detection → PR/ticket (fakes) | the above, all layers | Few |

## Layout and Markers

```
backend/tests/
  unit/        mirrors app/ (unit/domain/test_detector.py)
  integration/ mirrors app/ (integration/api/test_ingest.py)
  e2e/
  fixtures/    golden files: junit/<framework>/*.xml, yaml/, traces/
  fakes/       FakeGitHub, FakeJira, FakeSlack (implement the Protocols)
  builders.py  small functions that build test data: a_test(), a_run(), an_execution()
  conftest.py
```

- `@pytest.mark.integration` for anything needing Postgres; `make test` runs unit only, CI runs both.
- `pytest-randomly` is installed: tests run in random order and must pass in any order.
- `pytest-asyncio` in auto mode; async tests are plain `async def test_...`.

## Determinism Rules (CRITICAL)

- **No sleeping** to wait for work. Run tasks synchronously in tests or await them directly.
- **No real time.** Pass `now` or use a fixed clock fixture; for code that must read the clock, freeze it (`time-machine`).
- **No real network.** Fakes for integrations; `respx` for testing the real httpx clients against recorded responses.
- **No randomness without a seed.** Hypothesis uses its database/seed; any random IDs come from builders.
- **No shared state between tests.** Each DB test runs in a transaction rolled back at the end.
- **New or changed tests are run 10 times** before the PR: `pytest <file> --count=10 -p no:randomly`.

## Fixtures (conftest.py)

```python
@pytest.fixture(scope="session")
async def engine():
    # create fq_test schema via `alembic upgrade head` once per session
    ...

@pytest.fixture
async def session(engine):
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, join_transaction_mode="create_savepoint") as s:
            yield s
        await trans.rollback()

@pytest.fixture
async def client(app, session):
    app.dependency_overrides[get_session] = lambda: session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.fixture
def now():
    return datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
```

Keep fixtures small and composable. Prefer a builder function over a fixture when a test needs variations.

## Patterns by Area

### Domain rules (detector, policy, planner, state machine)

Table-driven, boundaries explicit:

```python
@pytest.mark.parametrize(
    ("occurrences", "groups", "expected"),
    [
        (1, 10, False),   # rate 10% but only 1 occurrence
        (2, 40, False),   # 2 occurrences, rate exactly 5% -> not above
        (2, 39, True),    # rate 5.1%
    ],
)
def test_quarantine_threshold(occurrences, groups, expected):
    assert meets_threshold(occurrences, groups, threshold=0.05, min_occurrences=2) is expected
```

State machine: one test per transition in architecture §11 and one per illegal transition.

### Parsers (JUnit normalizers, fingerprinting, masking)

- **Golden files:** input XML in `fixtures/junit/<framework>/`, expected normalized output as JSON next to it. Regenerate only on purpose (`--update-golden`), and review the diff.
- **Properties with hypothesis:** fingerprint is stable under changed numbers/UUIDs/timestamps; masking never leaves a token that matches a secret pattern; parse → serialize round-trips.

### API routes

Through the ASGI client, asserting status, body and DB state:

```python
async def test_duplicate_upload_is_stored_once(client, session, repo_token):
    files = junit_upload("pytest/fails_then_passes.xml")
    first = await client.post("/api/v1/ingest/runs", headers=auth(repo_token), files=files)
    second = await client.post("/api/v1/ingest/runs", headers=auth(repo_token), files=files)
    assert first.status_code == second.status_code == 202
    assert first.json()["upload_id"] == second.json()["upload_id"]
    assert await count(session, RawUpload) == 1
```

Always cover: happy path, 400 (schema), 401 (token), 413 (size), duplicate.

### Tasks and cron jobs

- Call the task function directly with the test session and fakes; assert DB state and fake calls.
- Always test **running it twice** produces the same result (idempotency).
- Test the failure path: fake raises → state is consistent and the task would retry.

### Integration clients

- Test the real client with `respx` routes that return recorded GitHub/Jira/Slack responses (fixtures under `fixtures/http/`), including 429 with `Retry-After` and 5xx.
- Everything else uses the fakes, which record calls: `assert fake_jira.created[0].labels == ["flaky_test"]`.

### Migrations

- `upgrade head` → `downgrade base` → `upgrade head` on an empty DB.
- Cascade test: delete a demo repository, every child table is empty (§15).

### pytest plugin (`plugins/pytest-flaky-reporter`)

- Use the `pytester` fixture to run tiny suites in-process and assert on the produced XML.

## Anti-Patterns

| Anti-pattern | Why it's bad | Instead |
|--------------|--------------|---------|
| `time.sleep()` / polling in tests | Slow and flaky | Run work synchronously, await it |
| `MagicMock` chains for Jira/GitHub | Tests the mock, not the behavior | Fakes implementing the Protocol |
| Mocking the DB or repositories | Misses SQL bugs | Transactional Postgres fixture |
| Asserting on log text | Brittle | Assert on state, return values, fake calls |
| One giant fixture building everything | Hidden coupling | Small builders |
| Tests that depend on order | Breaks under `pytest-randomly` | Isolate state per test |
| Golden files updated blindly | Hides regressions | Review every golden diff |
| Testing private helpers directly | Locks in structure | Test through the public function |
