# Development setup

How to run the project locally. `fq-admin` only has `version` so far; `seed-demo` and `purge-demo` arrive with later tasks, and those parts of this page are the target.

## Requirements

| Tool | Version |
|------|---------|
| Python | 3.12, managed with `uv` |
| Node | 22 LTS, with `pnpm` |
| Docker | with Compose v2 |

## First run

```bash
make setup      # uv sync, pnpm install, pre-commit install
cp .env.example .env
make up         # Postgres, migrations, API, worker, Grafana
make test       # unit tests
pytest -m integration
```

- API: `http://localhost:8000` (`/healthz`, `/readyz`, `/metrics`)
- Grafana: `http://localhost:3000`, login from `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` in `.env`
- Postgres: `localhost:5433` (`FQ_DB_HOST_PORT`), databases `fq` and `fq_test`
- `FQ_ENV` is `local` (readable console logs), `ci` or `prod` (JSON logs). If your `.env` still says `FQ_ENV=dev` from before M0-06, change it to `local`, or the API and worker will not start.

### Local environment

| Command | What it does |
|---------|--------------|
| `make up` | Builds the backend image, starts db, migrate, api, worker and Grafana, and waits until they are healthy |
| `make down` | Stops the stack and keeps the `pgdata` volume |
| `make reset-db` | Drops the volume and starts again: empty database, migrations re-applied |
| `make logs` | Follows the logs of all services |
| `make psql` | Opens `psql` on database `fq` as the owner role |
| `make integration` | Runs `pytest -m integration` against the running stack, with the host-side values from `.env` |
| `make smoke` | Checks `/healthz`, the `fq-postgres` Grafana datasource, `grafana_ro` read-only access and the image (non-root, under 300 MB) |

The `migrate` service runs `alembic upgrade head`, then installs the Procrastinate queue schema if it is missing.
Grafana reads the database through the read-only role `grafana_ro` (SELECT on the `reporting` schema only); the role and
both databases are created by `docker/postgres/init.sh` the first time the volume is initialised, so changes to that
script need `make reset-db`. The same applies to `POSTGRES_PASSWORD` and `GRAFANA_RO_PASSWORD`: changing them in `.env`
has no effect on an existing volume. Use URL-safe characters in the passwords, because they are embedded in database URLs.
Both `fq` and `fq_test` are migrated by the `migrate` service.

The backend image has one entrypoint with several roles: `api`, `worker`, `job <name>` and `migrate`.
All host ports are bound to `127.0.0.1`.

## Demo data

```bash
fq-admin seed-demo --days 28 --runs-per-day 3
fq-admin purge-demo     # removes every demo row
```

## Docs site

```bash
cd docs-site
pnpm install
pnpm dev        # syncs docs/ into the Engineering tab, then serves http://localhost:3000/docs
pnpm build      # static export to docs-site/out
```

## AI agent tooling: Headroom

The project is built with Claude Code agents (see `docs/agents.md`). [Headroom](https://github.com/headroomlabs-ai/headroom) cuts the tokens those sessions spend reading pytest output, CI logs, grep results and JSON by compressing them locally before they reach the model. Nothing in the repo depends on it; it's a per-developer setup.

```bash
uv tool install --python 3.13 "headroom-ai[all]"   # installs the `headroom` CLI
headroom doctor                                    # check the install and routing
```

| When | Command | What it does |
|------|---------|--------------|
| Every agent session | `headroom wrap claude` | Starts a local proxy and launches Claude Code through it; the proxy stops with the session |
| Always-on instead | `headroom deploy` | Persistent local proxy plus agent config (survives reboots) |
| After each milestone | `headroom learn` | Dry run: shows corrections learned from failed agent sessions in this repo |
| | `headroom learn --apply` | Writes them to `CLAUDE.local.md` (gitignored) and `MEMORY.md` |
| | `headroom learn --apply --target CLAUDE.md` | Writes to the shared `CLAUDE.md` instead — review the diff before committing |
| Any time | `headroom dashboard` / `headroom savings` | Live and historical token savings |
| Optional | `headroom mcp install` | Adds `headroom_compress`, `headroom_retrieve`, `headroom_stats` as MCP tools |

Rules for this repo:
- Keep learned corrections local (`CLAUDE.local.md`) until they've proved useful for a milestone; then move the good ones into `CLAUDE.md` in a normal PR.
- A learned correction never overrides `CLAUDE.md`, `docs/architecture.md` or a skill; if one contradicts them, delete it.
- Compression is local, but the compressed prompt still goes to the model provider. The secret-masking rules still apply to anything you paste into a session.

## Useful commands

| Command | What it does |
|---------|--------------|
| `make lint` / `make typecheck` | ruff, mypy, eslint, tsc |
| `make logs` | Follow API and worker logs |
| `make psql` | Open a Postgres shell |
| `make reset-db` | Drop and re-migrate the local database |
