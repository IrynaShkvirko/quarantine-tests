# Flaky Test Quarantine

Detects flaky tests from CI results (GitHub Actions and Jenkins), quarantines them without blocking builds, and drives each one to an owner, a Jira ticket and a verified fix.

Design spec: [`docs/architecture.md`](docs/architecture.md). Rules for contributors and agents: [`CLAUDE.md`](CLAUDE.md).

## Commands

```bash
make setup      # uv sync, pnpm install, pre-commit install
make lint       # ruff, eslint, prettier
make typecheck  # mypy, tsc
make test       # pytest and vitest unit tests
make up         # local environment: Postgres, migrations, API, worker, Grafana (needs .env)
make down
make reset-db   # drop the database volume and re-migrate
```
