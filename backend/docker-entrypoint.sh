#!/bin/sh
# One image, several roles: api | worker | job <name> | migrate. Anything else is exec'd as-is.
set -eu

role="${1:-api}"
[ "$#" -gt 0 ] && shift

case "$role" in
  api)
    if [ -n "${FQ_API_RELOAD:-}" ]; then
      exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000 --no-access-log --reload --reload-dir /app/backend/app
    fi
    exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000 --no-access-log
    ;;
  worker)
    exec python -m app worker
    ;;
  job)
    exec python -m app.jobs "$@"
    ;;
  migrate)
    # Local dev also migrates `fq_test` (integration tests); FQ_MIGRATE_TEST_DB is set by compose only.
    if [ -n "${FQ_MIGRATE_TEST_DB:-}" ]; then
      case "$FQ_DATABASE_URL" in
        */fq) test_url="${FQ_DATABASE_URL%/fq}/fq_test" ;;
        *) echo "FQ_MIGRATE_TEST_DB needs FQ_DATABASE_URL to end in /fq" >&2; exit 2 ;;
      esac
      alembic upgrade head
      FQ_DATABASE_URL="$test_url" exec alembic upgrade head
    fi
    exec alembic upgrade head
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
