# Development setup

How to run the project locally. The commands below arrive with M0-01 (repo skeleton) and M0-05 (local environment); until then this page is the target.

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
- Grafana: `http://localhost:3000`

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
