# Spike M0-10: rerun attempts in JUnit

**Question.** For pytest, Playwright and Jest, can every attempt of a rerun test (outcome, duration, failure message) end up in the JUnit XML we upload, and what must our reporters add?

**Answer.** Yes, for all three. None of them gets there with native JUnit output alone, so each plugin ships a small reporter.

**Decision.** One attempt representation for every framework: **one `<testcase>` per attempt, with `<property name="fq.attempt" value="N">`** (1 = first try), plus `fq.test_key` and a `file` attribute. Native rerun elements (`<rerunFailure>`, `<flakyFailure>`) are not used, because none of the three frameworks writes them. The conventions table in `docs/contracts/ingestion.md` §6 is updated to match.

Versions tested: Python 3.12, pytest 9.2.0 with pytest-rerunfailures 16.7; Node 22, Playwright 1.65.1; Jest 30.5.2 (jest-circus) with jest-junit 17.0.0.

Each spike project (`spikes/rerun-attempts/{pytest,playwright,jest}`) has the same cases: a stable test, fails-then-passes, fails-twice-then-passes, always-fails, a parametrized flaky test (`eu` flaky, `us` stable) and a nested test (class or `describe`). Reruns are configured as in architecture §9 (max 2 reruns, so 3 attempts).

Evidence:

- Our format, one file per framework: `docs/contracts/examples/junit-{pytest,playwright,jest}.xml`. In each, `fails twice then passes` has attempts 1 and 2 with a `<failure message>` and attempt 3 without, and `always fails` has three failures.
- Native output for comparison: `docs/spikes/rerun-attempts-{pytest,playwright,jest}-native.xml`. Local absolute paths are replaced with `<repo>` and the hostname with `ci-runner`.
- Prototype reporters: `spikes/rerun-attempts/pytest/conftest.py`, `playwright/fq-reporter.ts`, `jest/fq-reporter.js`.

## pytest

| | |
|---|---|
| Native support | `--junitxml` already writes **one `<testcase>` per attempt** with the same `classname` and `name`. |
| What's missing | The failed reruns have **no `<failure>` element**, so attempts 1 and 2 of a fails-twice test look like passes. Rows carry no attempt number or `file` attribute, and no `fq.test_key`. Nothing in the XML tells a reader which row is the last. |
| Chosen approach | A `conftest.py` hook on `pytest_runtest_logreport`. pytest-rerunfailures sets `report.outcome == "rerun"` on each failed attempt that will be retried, so the hook records every `call` report and counts attempts per node id. The failure message comes from `report.longrepr.reprcrash.message`. |
| Effort | Small: about 60 lines for the prototype. M1-06 adds options (output path, tags, skip markers) and tests. |

## Playwright

| | |
|---|---|
| Native support | The `junit` reporter writes **one `<testcase>` per test**, so retries are collapsed. A flaky test is a passing row with attachment paths in `<system-out>`; an always-failing test has one `<failure>` that concatenates all retries as text. The `json` reporter has `results[]` with `retry`, `status` and `duration` per attempt, and a test-level `status` of `flaky`. |
| What's missing | Per-attempt rows, outcome and duration in JUnit; `file`; `fq.test_key`. Describe titles are joined with ` › ` (Unicode), which differs from the ` > ` in the spec's §3.1 examples. |
| Chosen approach | A custom reporter. `onTestEnd(test, result)` is called once per attempt with `result.retry` (0-based), `result.status`, `result.duration` and `result.error.message`. The reporter writes one `<testcase>` per call with `fq.attempt = retry + 1`. The test name is `titlePath().slice(3)` (drops the empty root, project and file entries) joined with ` > `. ANSI colour codes are stripped from messages. |
| Effort | Small to medium: about 50 lines for the prototype. M5-01 adds tags (`test.info().annotations` or title tags), skip markers (`fixme`, `skip`) and Vitest tests. |

## Jest

| | |
|---|---|
| Native support | `jest-junit` writes **one `<testcase>` per test**, so retries are collapsed and a flaky test is a plain pass. Its defaults are also unusable as a test key: `classname` and `name` are both the full title joined with spaces (`cart total discount applies discount`), and the `<testsuite>` name is `undefined` without configuration. |
| What's missing | Per-attempt rows; `file`; `fq.test_key`; unambiguous describe nesting. |
| Chosen approach | A custom reporter. In Jest 30 with jest-circus, `onTestCaseResult(test, result)` is called **once per attempt**, and each call carries that attempt's own `status`, `duration` and `failureMessages`; `invocations` is the attempt number (1, 2, 3). `retryReasons` on the final call repeats the earlier failures, so it isn't needed. `ancestorTitles` gives the describe nesting. |
| Effort | Small: about 40 lines for the prototype. M5-02 writes it in TypeScript and adds tags, skip markers (`it.skip`) and tests. |

## Test key parts (§3.1)

| | pytest | Playwright | Jest |
|---|---|---|---|
| File | Not written natively. `report.nodeid` starts with the path relative to pytest's rootdir. | Not written natively. Path relative to the repo root (`FQ_REPO_ROOT`, else the nearest `.git`), `/`-separated. | Not written natively. Same rule as Playwright. |
| Name | `Class::test_name[param]` from the node id after the file. | `describe > describe > title` from `titlePath()`. | `ancestorTitles` + `title` joined with ` > `. |
| Parametrized | pytest writes `[eu]` into the node id. | Playwright has no built-in parametrize; loops generate distinct titles (`param flaky [eu]`), which are already unique. | `test.each` expands the title (`param flaky [eu]`) before the reporter sees it. |
| Nested | Class name is part of the node id (`TestNested::test_in_class`). | `Checkout > saved card > pays`. | `cart total > discount > applies discount`. |

## Edge cases and fallbacks

None of these blocks the design; each lists how we handle it.

1. **Native pytest XML hides failed reruns.** Anyone feeding plain `--junitxml` output to the backend would see three passing rows for a fails-twice test. Fallback: the backend must not accept JUnit without `fq.attempt`, or must treat a missing `fq.attempt` as "attempt data unavailable", never as a first-try pass. The detection rules need this distinction (§3.4 `rerun` evidence), so M1-02 should reject or flag such uploads. Needs a decision in M1.
2. **rootdir changes the path.** pytest builds node ids relative to its rootdir. A rootdir at the repo root gives `tests/api/test_orders.py`, but running from a subfolder with its own `pytest.ini` gives a path relative to that subfolder. We hit this in the spike: once the repo's root `pyproject.toml` existed, node ids in the sample became `spikes/rerun-attempts/pytest/test_sample.py`, until the spike folder got its own `pytest.ini`. The plugin should compute `file_path` relative to the git root, not the pytest rootdir, or the adapter must pass the base directory. Playwright (`config.rootDir`) and Jest (`globalConfig.rootDir`) have the same problem in a monorepo where the config isn't at the repo root, and `path.relative` gives `\\` separators on Windows. The Playwright and Jest prototypes now compute the path from `FQ_REPO_ROOT` (set by the adapter) or the nearest `.git` and normalise to `/`; the sample keys are `playwright::spikes/rerun-attempts/playwright/sample.spec.ts::...`. The pytest prototype still uses the node id (M1-06).
3. **Playwright projects.** `titlePath()` includes the project name (for example `chromium`), and the same test runs once per project with the same file and title. The key drops the project, so the same test in two browsers gives identical keys. `environment` (§3.3) separates them, but only if the adapter runs each project as its own upload. Not tested with multiple projects in this spike; M5-01 must check it.
4. **Jest retry order.** With `retryTimes`, jest-circus reruns failed tests after the rest of the describe block, so attempt rows for one test are not adjacent in the callback stream (observed: all first attempts, then second attempts). The reporter must not assume adjacency. It writes rows in callback order, and the backend orders by `fq.attempt`.
5. **Jest attempt number depends on `invocations`.** It's the 1-based count in Jest 30. We haven't checked older Jest versions. M5-02 should pin a minimum Jest version (30) and fail clearly on others.
6. **Jest and Playwright duplicate titles.** Two tests with the same title in the same file (allowed by both) give the same key. pytest can't have this, since node ids are unique. Fallback: the reporters append a `#2`-style suffix to later duplicates, or the skip lint flags them. Not implemented in the spike.
7. **Failure messages.** The prototypes keep only the first line (capped at 1000 characters in pytest), with ANSI codes stripped; §6 now requires this, because pytest's assertion rewriting puts repr'd local values in later lines. That is enough for the signature (§3.6), but the full text is wanted for the Jira ticket. Decide in M1-06 whether to carry the full text as a masked `<failure>` body.
8. **Setup and teardown failures (pytest).** The prototype records `setup` failures and the `call` phase; `teardown` failures aren't recorded. M1-06 decides how to attribute them (probably as an error on the last attempt).
9. **Skipped and xfail.** The sample projects have no skipped tests, so `fq.skip_marker` isn't exercised in the examples. The table in `ingestion.md` §6 stays as designed; M1-06, M5-01 and M5-02 each add a skipped case to their tests. Probes during review found three traps, now handled in the prototypes:
   - **pytest:** a skip's `longrepr` is a `(path, line, "Skipped: reason")` tuple with no `reprcrash`, and an xfail's reason is in `report.wasxfail`. Reading `reprcrash` alone gave `<skipped message="">`.
   - **Jest:** `test.skip` and `describe.skip` never reach `onTestCaseResult`. They only appear in the file-level `onTestResult`, so the reporter adds skipped rows there for tests it hasn't seen. `todo` and `disabled` are skips too, not passes.
   - **Playwright:** an `interrupted` attempt (the run stopped mid-test, for example `--max-failures` in a stress run) was written as a pass row, which would fake fail-then-pass evidence. The prototype omits it. M1 should confirm that an interrupted attempt is never evidence.
   - **Playwright `test.fail()`:** comparing `result.status` alone wrote an expected failure as `<failure>` on every attempt. The prototype compares with `test.expectedStatus`: failing as expected is a pass row, passing unexpectedly is a failure (`expected to fail (test.fail) but passed`). Verified with a probe spec.
   - **Jest unknown statuses:** any status other than `passed`, `failed` or the skip statuses was written as a pass. The prototype now refuses it: no row, and `getLastError()` makes Jest exit non-zero. `test.todo` was verified to give a `<skipped/>` row.
10. **pytest-xdist.** Workers load the conftest too and ran `sessionfinish` with only their own subset, racing the controller on the same `--fq-junit` path. The prototype now writes only on the controller (no `config.workerinput`). Checked with `-n 2 --reruns 2`: the same 13 rows (keys and attempts) as a serial run. M1-06 must keep an xdist test.
11. **Illegal XML characters.** None of the prototypes strips characters illegal in XML 1.0, and the TS/JS ones escape only `& < > "`. A control character in a test title makes the file unparseable, so §6 requires a shared sanitizing escaper (golden test plus a hypothesis property). The TS/JS prototypes build XML by string concatenation, which is safe only while every value goes through `esc()`; the real plugins should use an XML writer. They must also not write debug dumps like the Jest prototype's `native-testcase-results.json` (full failure text) in CI.
12. **Key collisions.** `fq.test_key` joins parts with ` > `, so describe `a` plus title `b` collides with a title `a > b`. §6 now treats the key as an opaque, length-capped string; collisions are rare and handled like the duplicate-title case (6).
13. **Durations.** pytest, Playwright and Jest each give a per-attempt duration, so no framework needs the "total only" fallback.

## Effort summary

| Framework | Native support | Approach | Effort | Used by |
|---|---|---|---|---|
| pytest | One row per attempt, failures missing on reruns | Hook on `pytest_runtest_logreport` | S | M1-06 |
| Playwright | Collapsed; per-attempt data only in the JSON reporter | Custom reporter on `onTestEnd` | S–M | M5-01 |
| Jest | Collapsed; per-attempt callback in Jest 30 | Custom reporter on `onTestCaseResult` | S | M5-02 |

## Follow-ups (not done here)

- Decide in M1 how the backend treats an upload with no `fq.attempt` (edge case 1).
- Add a skipped test and an xdist run to the M1-06 plugin tests; add `test.fail()` and `test.todo` cases to M5-01 and M5-02; check multi-project Playwright in M5-01.
- The prototypes are starting points only: M1-06, M5-01 and M5-02 rewrite them under `plugins/` with types, tests and the options listed above. The Jest prototype is JavaScript; M5-02 must be TypeScript strict.
