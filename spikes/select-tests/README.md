# spikes/select-tests

M0-11 throwaway prototypes: run all tests except / only the tests listed in `quarantine.yaml`.
Findings and decision: [`docs/spikes/select-tests.md`](../../docs/spikes/select-tests.md).

```bash
pnpm install --ignore-workspace
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python pytest pyyaml
.venv/bin/python generate.py   # 500-test suites + quarantine lists into .generated/
.venv/bin/python run_all.py    # exactness, skipped count and timings -> results/results.json
```

| Path | What |
|------|------|
| `pytest/fq_select_plugin.py` | pytest plugin (`--quarantine-file=`, `--quarantine-mode=`, or `FQ_QUARANTINE_*`) |
| `playwright/quarantine-select.ts` | `grep` / `grepInvert` builder and `--test-list` file writer |
| `jest/quarantine-select.js`, `register-filter.js`, `empty-suite-reporter.js` | Jest registration filter (recommended) |
| `jest/run-with-name-filter.js` | the `-t` approach, kept only to show why it fails |

The list always comes from a file (`FQ_QUARANTINE_FILE`), mode from `FQ_QUARANTINE_MODE=exclude|only|off`.
