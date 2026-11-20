# M0 issues

Issue bodies for milestone M0 (Foundations + risk spikes), generated from the M0 Task Breakdown doc. `scripts/github/create_m0_issues.sh` creates them on GitHub. Each file starts with a small header (`title`, `labels`, `depends`) that the script reads; everything after `---` is the issue body. `{{DEPENDS}}` is replaced with issue links after all issues exist.

M0-03's import script later takes over these issues through the `fq-task-id` marker and creates M1–M7.

**Issue format.** Title `[M0-xx] <name>`. Labels: `milestone:M0` plus the component (`infra`, `backend`, `ci`, `plugins`, `integrations`, `docs`) and `spike` for M0-10 to M0-12. Every body has the same parts: Context, Implementation, Out of scope, Acceptance criteria, Tests, Depends on. M0-03's import script splits a Markdown export of this doc on the `### M0-` headings.

**Shared stack decisions** (apply to every task; pin each tool to its current stable release when M0-01 is done and record versions in the lockfiles):

| Area | Decision |
| --- | --- |
| Python | 3.12, `uv` workspace with one `uv.lock` at the root |
| Python quality | `ruff` (lint + format), `mypy --strict` on `backend/app/domain` and `backend/app/config`, standard mypy elsewhere |
| Python tests | `pytest`, `pytest-asyncio`, `pytest-cov`, `hypothesis` for property tests |
| Node | 22 LTS, `pnpm` workspace, TypeScript `strict`, `eslint` + `prettier`, `vitest` for plugin unit tests |
| Backend | FastAPI, pydantic v2, pydantic-settings, SQLAlchemy 2.0 async on psycopg 3, Alembic, Procrastinate (also psycopg 3), structlog, prometheus-client |
| Data and dashboards | PostgreSQL 16, Grafana OSS |
| CI helper | New `ci/fq-cli/` Python package: one CLI (`fq`) used by both the GitHub Actions and the Jenkins library for fetch-quarantine, gate and upload. This adds one folder to the §16 layout |

**Order of work.** Tasks in the same wave can run in parallel, one agent each:

1. **Wave 1:** M0-01 (everything else needs the repo). The three spikes M0-10, M0-11, M0-12 and the contract draft M0-08 need no code from the repo and can start the same day in scratch folders.
2. **Wave 2:** M0-02, M0-04, M0-05, M0-13.
3. **Wave 3:** M0-03 (needs the templates from M0-02), M0-06 (needs the dev environment).
4. **Wave 4:** M0-07 and M0-09, both on the backend skeleton.
5. **Done when:** all 13 issues are closed, `main` is green, and the spike findings are merged into `docs/spikes/`.
