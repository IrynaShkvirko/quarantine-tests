# Spike M0-11: select tests by ID (include / exclude)

Status: done, findings below. Prototype code: `spikes/select-tests/` (reused by M3-08, M5-01, M5-02).
Spec sections: `docs/architecture.md` §3.1, §4.3, §9.

## Question

Given the test keys in `quarantine.yaml`, can each framework (a) run everything except those tests and
(b) run only those tests, exactly, without the excluded tests showing up as skipped?

## Answer

| Framework | Mechanism | Exact (480 / 20) | Skipped in JUnit | 300 keys |
|-----------|-----------|------------------|------------------|----------|
| pytest | Plugin: `pytest_collection_modifyitems` + `pytest_deselected` | yes | 0 | yes, no slowdown |
| Playwright | **`--test-list` / `--test-list-invert <file>`** (recommended) | yes | 0 | yes, no slowdown |
| Playwright | `grep` / `grepInvert` built in `playwright.config.ts` (fallback) | yes | 0 | yes, but **87 s** with long keys (see below) |
| Jest | **Registration filter**: `setupFilesAfterEnv` wraps `describe` / `test` / `it` (recommended) + `empty-suite-reporter` | yes | 0 | yes, +1 s |
| Jest | `-t` with a name regex (the §9 approach) | **no** | **20 / 480** | n/a |

All three recommended mechanisms ran exactly the 480 non-listed tests in exclude mode and exactly the 20 listed
tests in only mode, on a 500-test suite per framework. The list contains every hard case **except** titles with
` > ` for Playwright: those live in a separate mini suite (`playwright-gt`) because neither Playwright mechanism can
select them, so for that one case the acceptance criterion is **not met** for Playwright (see Hard cases). The oracle is the set of
executed keys, compared for equality (`run_all.py`), not just a count.

### Decision

1. **How the list reaches the framework:** always a file path, `FQ_QUARANTINE_FILE`, plus
   `FQ_QUARANTINE_MODE=exclude|only|off`. Never inline on the command line.
2. **pytest:** plugin option `--quarantine-file` / `--quarantine-mode` defaulting to those env vars.
3. **Playwright:** `fq` converts the YAML into a test-list file and passes `--test-list-invert` (blocking job) or
   `--test-list` (quarantine job). Keep the `grep` builder as a fallback for Playwright versions without the flag.
4. **Jest:** do not use `-t` / `--testPathPattern` as §9 describes. Use the registration filter, configured through
   `jest.config.js` + env. Only mode additionally narrows `testRegex` to the files that contain listed tests.

## Security requirements for the adapters (M3-08, M5-01, M5-02)

From the security review of this spike. The prototypes are throwaway and do not implement these.

1. **Provenance.** The file in `FQ_QUARANTINE_FILE` must be the default-branch copy (`git show origin/main:quarantine.yaml`)
   or the backend's response, never the PR head's working tree. The examples above use a local path only because the
   spike has no PR. Otherwise a human PR can add its own failing test to `quarantine.yaml` and drop it from the blocking
   run. The bot-PR checks (§9.5) do not cover that. The same applies to the gate's safety net (§4.3): "a missed exclusion is
   still non-blocking" only holds if the gate also uses the trusted list.
2. **Validate once, in `fq`, not in the plugins.** `fq` parses the YAML (safe load, schema) and hands each adapter a plain
   list. Validation: known prefix, `::` present, single line, no control characters, non-empty title, length cap per key,
   cap on entry count. The prototypes skip this: a key without `::` is not rejected, and a key containing a newline would add
   lines to the Playwright test-list file, where a line naming a file or describe selects everything under it (prefix
   semantics). Plugins that read a pre-validated list also drop the PyYAML / `yaml` runtime dependency.
3. **Fail closed on configuration.** Whitelist `FQ_QUARANTINE_MODE` (`off|exclude|only`) and fail the job on any other
   value. Fail when the mode is not `off` and the file is unset, missing or unreadable, in all three adapters. The
   prototypes are inconsistent: pytest raises, Playwright and Jest return an unfiltered config (so `only` runs everything).
4. **Reconcile after the run.** A quarantine or verification job that executes 0 tests, or fewer than the keys in its list,
   must not count as a pass or a verified fix. Causes seen in the spike: Playwright `--test-list` matching nothing (exit 0),
   pytest nodeid prefix mismatch, Jest run from a directory other than `rootDir` (`register-filter.js` computes paths
   from `process.cwd()`).
5. **Scope the Jest empty-suite suppression.** `empty-suite-reporter.js` hides every empty file in exclude mode. Production
   code should suppress it only when every test key for that file is in the list.
6. **Do not ship Playwright `grep` without a pattern-size cap** (the file is influenced by PRs; see the size cliff). Prefer
   `--test-list`.
7. **`escapeRegExp` escapes `-` and `/`**, valid only for regexes without the `u` / `v` flag. Copy it with a property test.
8. Whatever is added for `.each` / `.concurrent` / `.failing` / `.todo` in Jest needs a test that fails if a listed test runs.

## Spec conflicts to resolve (not edited here)

`CLAUDE.md` says to stop and ask when a task and the spec disagree, so the spec is unchanged except for the D11 change
below, which the owner asked for. Everything else in this list still needs a decision from the owner:

- **§9 table, Jest rows** say `-t` negative-lookahead and `--testPathPattern` + `-t`. The spike shows that approach
  fails both acceptance criteria (see "Jest `-t`" below). Proposed: replace with the registration filter.
- **§9 table, pytest row** shows `--quarantine-file q.yaml` (space form). That form silently breaks nodeid matching
  (see pytest section). Proposed: document `--quarantine-file=q.yaml` or `FQ_QUARANTINE_FILE`.
- **§9 table, Jest `--testPathIgnorePatterns` for whole files**: not evaluated by this spike. The registration filter
  needs no file-level ignore in exclude mode (the empty-suite reporter handles fully quarantined files).
- **§9 table, Playwright rows** say config-built `grepInvert` / `grep`. It works, but `--test-list` is simpler and
  has no regex size cliff. Proposed: mention `--test-list` as the primary.
- **D11 (decision log, line 45)** said CI falls back to the checkout's copy of `quarantine.yaml` if the default-branch
  fetch fails, which fails open towards PR-controlled input (see requirement 1). **Changed in `docs/architecture.md`**
  on the owner's request: fall back to the backend's last-known-good list, and fail the job if that is unavailable
  too; the gate uses the same fetched list as test selection. Edited locations: `docs/architecture.md` D11, §4.3 safety
  net, §8.1 (new repo-token endpoint `GET /api/v1/repos/{repo}/quarantine`), §9.1 flowchart (fetch fallback and gate
  node), §13 (repo-token scope and Ingress allow-list); `docs/ingestion-flow.md` (sequence and the "CI depends on the
  backend only as a fallback" property); `docs-site/content/docs/architecture/ci-cd-flows.mdx` (both diagrams).
  Implementation belongs to the M-tasks that build `fq fetch-quarantine`, `fq gate` and the API.
- **§3.1 key format** is ambiguous when a title contains ` > ` (see "Hard cases"). Not fixable in the plugins.

## Method

- Fixture per framework: 500 tests in 28 files, 20 listed. Generated by `generate.py` into `spikes/select-tests/.generated/`.
- The 20 listed keys per framework mix plain tests with hard cases. Decoys (similar but not listed) stay in the run:
  pytest `[1]` vs `[10]`, `[a[b]c]` vs `[a[b]`, `x::y` vs `x::z`; Playwright / Jest "Outer > nested" vs
  "Outer > Inner > nested", and two files with the same `Dup > same title`.
- Versions: pytest 9.2.0, Playwright 1.65.1, Jest 30.5.2, jest-junit 16.0.0, Node 22.23.5, Python 3.12, macOS arm64.
  One machine, Playwright with 4 workers, medians of 5 runs.
- Run it: `cd spikes/select-tests && pnpm install --ignore-workspace && uv venv --python 3.12 .venv &&
  uv pip install --python .venv/bin/python pytest pyyaml && .venv/bin/python generate.py && .venv/bin/python run_all.py`.
  Raw numbers land in `spikes/select-tests/results/results.json` (gitignored).

## pytest

Key = `pytest::` + `item.nodeid`, matched by exact string equality (no parsing, so `::`, brackets, spaces and regex
characters inside parameters need no escaping). Non-matching items go through `config.hook.pytest_deselected`, so they
are neither run nor reported as skipped, and `--junitxml` contains only the executed tests (`tests="480"`, 0 `<skipped>`).
The terminal still prints `20 deselected`, which is fine.

Behaviors to know:

- **Unicode params are escaped in the nodeid** by pytest (`café-日本` becomes `caf\xe9-日本`). The key in
  `quarantine.yaml` must be the nodeid form. The normalizer (M1) must emit the same form that JUnit reports; JUnit also
  uses the escaped form, so this is consistent as long as keys come from JUnit.
- **Pass the file as `--quarantine-file=PATH` or via `FQ_QUARANTINE_FILE`, never `--quarantine-file PATH`** (space
  form). pytest's early argument parsing does not know our option takes a value and treats `PATH` as a test path; the
  rootdir then moves up to the git root and every nodeid gets a path prefix, so nothing matches (silent: exclude removes
  nothing, only selects nothing). Verified with `-p fq_select_plugin`; registration through an entry point was not tested.
- nodeids are relative to pytest's rootdir. In a monorepo where rootdir is not the repo root, the plugin must rebase
  to the repo-root-relative path used in §3.1. Not covered by this spike.

## Playwright

**`--test-list` (recommended).** Present in the installed 1.65.1 (`--test-list`, `--test-list-invert`; CLI only, no
config key). Line format is `file > describe > ... > title`, with `#` comments allowed. Matching is by exact titles
along the path, so no regex escaping is needed. Semantics to know:

- It is a **prefix** match on the title path: a line naming a `describe` selects everything under it.
- Lines are split on `>` (or `›`), so a title that contains `>` can never be matched (see Hard cases).
- A list that matches nothing exits 0 with an empty run (`tests="0"`). The adapter must check the test count
  (§9.1 already fails on count 0 for the blocking job; the quarantine job needs the same check for only mode).
- Output has 0 skipped and exactly 480 / 20 tests, also with 300 keys (1.8 s / 1.0 s).

**`grep` / `grepInvert` (fallback).** Playwright matches the regex against `titlePath().join(' ')`, which is
`<project> <file> <describes...> <title>`. The builder escapes each title and joins with spaces, anchored with
`(?:^|\s)...$`. Exact for all hard cases, 0 skipped. Caveats:

- **Size cliff.** One alternation regex is fast until the pattern passes about 50–60 KB, then V8 slows by 100x:
  500 matches take 15 ms at 51 KB and 1.6 s at 62 KB, and 43 s at 202 KB. Playwright applies it repeatedly, so
  300 keys of ~700 chars each (pattern 203 KB) took 87 s for the whole run versus 1.5 s. 300 realistic keys
  (~100 chars, ~30 KB) are fine. Anchoring the start does not help. If grep is used, split the list across several
  invocations or fall back when the pattern is larger than ~40 KB.
- Regex characters in titles are handled by escaping `. * + ? ^ $ { } ( ) | [ ] \ / -`.

## Jest

**Registration filter (recommended).** `setupFilesAfterEnv` wraps `describe` (keeps a name stack) and `test` / `it`
(computes `relative-file::describe > ... > title` and skips registration when filtered out). Excluded tests never exist
for Jest, so they are not reported at all: 480 / 20 exact, 0 skipped, including regex characters, quotes, `>` in a
title, unicode, nested describes and same-title-in-two-files.

- **Empty files fail.** Jest fails any file with zero registered tests ("Your test suite must contain at least one
  test.", raised in `@jest/core`, not in the runner). In exclude mode that hits every file whose tests are all
  quarantined (`dup_a.test.js` in the fixture) and `jest` exits 1, while jest-junit prints nothing for it, so it is easy
  to miss. The prototype's `empty-suite-reporter.js`, listed before jest-junit, removes exactly that failure from the
  counters. **It edits Jest result internals** (`numFailedTestSuites`, `numRuntimeErrorTestSuites`,
  `numTotalTestSuites`); pin the Jest version in M5-02 and keep a test for it.
- Not wrapped yet: `test.each` / `describe.each` (names are interpolated by Jest), `test.concurrent`, `test.failing`,
  `test.todo`. They pass through unfiltered, so a quarantined parametrized test would still run. M5-02 must cover them
  (wrap `.each` and format titles the same way Jest does).
- The aliases `fit`, `xit`, `xtest`, `fdescribe` and `xdescribe` are not wrapped either, so a quarantined `fit(...)`
  still runs in exclude mode and an unlisted `xit(...)` shows up as skipped in only mode. M5-02 must wrap every global.
- Only mode's `testRegex` (`/<file>$`) is not anchored on `rootDir`, so `pkg/a.test.js` also loads for a key on
  `a.test.js`. Those files register 0 tests and the empty-suite reporter hides it. M5-02 must anchor the pattern.
- Only mode sets `testRegex` to the files that contain listed tests, so other files are not even loaded.

**`-t` name regex (the §9 approach), measured through `jest.run()` so the command line is not a factor.** Fails:

- JUnit has `<skipped/>` for every filtered test: 20 in exclude mode, 480 in only mode.
- `-t` sees only `describe test` joined by single spaces, **no file**. Two tests with the same name in different files
  cannot be told apart: exclude also dropped `dup_b` (not listed), only also ran `dup_b`.
- A name containing ` > ` cannot be rebuilt from the key by splitting on ` > `, so `arrow a > b in title` was missed
  (it ran in exclude mode and was not selected in only mode).
- `-t` (`testNamePattern`) is a CLI / global option, not a per-project config key. Passing it on a real command line hits the
  per-argument limit (Linux `MAX_ARG_STRLEN` is 128 KiB; not measured here, macOS allows 1 MiB). A 300-key regex of long
  keys is ~200 KB.
- `--testPathPattern` (renamed `--testPathPatterns` in Jest 30) only selects files, so it cannot remove tests inside a
  file.

**Custom `testSequencer` / test environment: not prototyped.** From the API shape only: a sequencer works on the list of
test **files** (sort / shard), so it cannot drop a single test; a custom environment's `handleTestEvent` receives
`add_test` after the test is registered, so the available action there would be marking it skipped, the outcome we want
to avoid. The registration filter does the job from `setupFilesAfterEnv` without either.

## Hard cases

| Case | pytest | Playwright test-list | Playwright grep | Jest register | Jest `-t` |
|------|--------|----------------------|-----------------|---------------|-----------|
| Brackets, spaces, `::` in params | ok | n/a | n/a | n/a | n/a |
| Unicode / emoji in title | ok (escaped form) | ok | ok | ok | ok |
| Regex chars `( ) [ ] . * + ? $ ^ \|` | ok | ok | ok (escaped) | ok | ok (escaped) |
| Quotes, backticks | ok | ok | ok | ok | ok |
| Nested `describe` + decoy one level up | ok (classes) | ok | ok | ok | ok |
| Same title in two files, one listed | ok | ok | ok | ok | **fails** |
| Title containing ` > ` | n/a | **never matches, exits 0 with 0 tests** | **never matches**, `No tests found`, exit 1 | ok (string equality), see below | **fails** |
| 300 keys | ok | ok | ok below ~50 KB, else slow | ok | not exact either (same failures as above, measured) |

**` > ` in titles is a key-format problem (§3.1).** `describe "A"` + `test "B > C"` and `describe "A > B"` + `test "C"`
both produce `A > B > C`. Registration filtering by string equality selects both (over-selection, never
under-selection), the Playwright mechanisms select neither. Only a different separator in the key would remove the
ambiguity. Because the blocking job keeps the quarantine gate (§4.3 safety net), a missed exclusion is still non-blocking.

## Overhead on 500 tests

Median of 5 runs, wall clock including process start; numbers are from `results/results.json` of the last full run
(re-runs vary by about ±0.1 s). The suite is trivial (`expect(1).toBe(1)`), so these numbers are selection +
framework overhead, not test time.

| Framework | Plain | Exclude | Only | Notes |
|-----------|-------|---------|------|-------|
| pytest collect only | 0.159 s | 0.178 s | 0.171 s | plugin cost within noise |
| pytest full run | 0.241 s | 0.253 s | 0.177 s | |
| Playwright `--list` | 0.418 s | 0.415 s (grep) | 0.414 s (grep) / 0.570 s (test-list) | |
| Playwright full run | 1.594 s | 1.542 s grep / 1.826 s test-list | 0.793 s grep / 0.975 s test-list | 4 workers, noise about ±0.2 s |
| Jest full run | 0.789 s | 0.948 s (register) / 0.836 s (`-t`) | 0.644 s (register) / 0.710 s (`-t`) | Jest has no collect-only mode |

Selection overhead is within run-to-run noise for pytest and Playwright at 500 tests. The Jest registration filter
adds a small but consistent ~0.1–0.16 s in exclude mode (seen in three full runs), from loading the YAML in every test
file's VM; reading a pre-validated list from `fq` (security requirement 2) should shrink it. The one measured
exception is the Playwright grep regex above ~50 KB (the regex timings in that section are from ad-hoc Node
scripts, not part of `run_all.py` or `results.json`; only the 87 s end-to-end figure is). With 300 keys (20 real + 280 padding): pytest 0.8 s, Playwright
test-list 1.8 s / 1.0 s, Jest register 1.7 s / 1.7 s.

## Limits of this spike

- One machine (macOS arm64); the Linux argument-length limit is cited, not measured.
- **Playwright paths assume `testDir: '.'`.** Both mechanisms compare the key's repo-relative path (§3.1) with
  Playwright's file path, which is relative to `testDir` (grep) or `rootDir` (test-list). The fixture config uses
  `testDir: '.'` at the suite root, so they line up. In a repo with `testDir: 'e2e'` or a config in a subfolder, nothing
  would match (exclude removes nothing, only runs 0 tests). M5-01 must rebase keys onto the Playwright root.
- Fixture tests are trivial and Playwright / Jest do not launch browsers or jsdom; real suites make selection overhead
  proportionally smaller, not larger.
- The pytest entry-point registration, monorepo rootdir rebasing, pytest-xdist and pytest-split interplay, Playwright
  multi-project configs (project name is part of the grep string) and Jest `projects` / `--shard` interplay were not tested.
- Whether Playwright versions older than 1.65 have `--test-list` was not checked; M5-01 must pin a minimum version.

## Follow-ups (not done here)

- Owner decision on the spec items above, then update `docs/architecture.md` §9 (and §3.1 if the separator changes).
- M3-08: package the pytest plugin; decide how nodeids are rebased in a monorepo.
- M5-01: Playwright adapter writes the test-list file; add the zero-test check for only mode.
- M5-02: harden the Jest registration filter (`each`, `concurrent`, `failing`, `todo`) and pin Jest.
