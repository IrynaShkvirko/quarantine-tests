# backend

FastAPI service, Procrastinate worker, cron entrypoints and the `fq-admin` CLI. Layout: see CLAUDE.md.

Run it locally with `make up` from the repo root (see `docs/development-setup.md`). One image (`backend/Dockerfile`, built from the repo root) serves every role through `docker-entrypoint.sh`: `api`, `worker`, `job <name>` and `migrate`.
