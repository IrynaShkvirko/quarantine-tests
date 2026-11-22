# backend

FastAPI service, Procrastinate worker, cron entrypoints and the `fq-admin` CLI. Layout: see CLAUDE.md.

Run it locally with `make up` from the repo root (see `docs/development-setup.md`). One image (`backend/Dockerfile`, built from the repo root) serves every role through `docker-entrypoint.sh`: `api`, `worker`, `job <name>` and `migrate`.

## Endpoints and commands

- `GET /healthz`: process is alive (no database). `GET /readyz`: database reachable and the Procrastinate schema installed, else 503. `GET /metrics`: Prometheus.
- `python -m app worker`: Procrastinate worker. `fq-admin version`: admin CLI (later tasks add commands).
- Settings come from `FQ_*` variables (`app/settings.py`). `FQ_ENV` is `local` (console logs), `ci` or `prod` (JSON logs).
- Migrations: `cd backend && alembic upgrade head`. The Procrastinate queue schema is one of them.
- Tests: `make test` (unit); `make integration` or `pytest -m integration` needs `make up` or a Postgres in `FQ_DATABASE_URL`. The suite recreates the `fq_test` database itself.
