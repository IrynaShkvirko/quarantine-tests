#!/bin/sh
# Acceptance checks for the local environment (M0-05). Run after `make up`.
# Reads host ports and credentials from .env (falls back to .env.example).
set -eu

cd "$(dirname "$0")/.."
env_file=.env
[ -f "$env_file" ] || env_file=.env.example
set -a
# shellcheck disable=SC1090
. "./$env_file"
set +a

api_port="${FQ_API_HOST_PORT:-8000}"
grafana_port="${GRAFANA_HOST_PORT:-3000}"
probe=reporting.grafana_ro_probe
fail=0

check() { # check <label> <command...>
  label="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "PASS  $label"; else echo "FAIL  $label"; fail=1; fi
}

# Connects over the container network (-h db), so the grafana_ro password is really verified.
psql_ro() { docker compose exec -T -e PGPASSWORD="$GRAFANA_RO_PASSWORD" db \
  psql -h db -U grafana_ro -d fq -v ON_ERROR_STOP=1 -tA "$@"; }
psql_owner() { docker compose exec -T db psql -U fq -d fq -v ON_ERROR_STOP=1 -tA "$@"; }
# Credentials go through stdin (-K -), so they never appear in `ps`.
grafana_get() { printf 'user = "%s:%s"\n' "$GRAFANA_ADMIN_USER" "$GRAFANA_ADMIN_PASSWORD" \
  | curl -fsS -K - "$1"; }
datasource_ok() { grafana_get "http://127.0.0.1:${grafana_port}/api/datasources/uid/fq-postgres/health" \
  | grep -q '"status":"OK"'; }
databases_exist() { [ "$(docker compose exec -T db psql -U fq -d postgres -tA \
  -c "SELECT count(*) FROM pg_database WHERE datname IN ('fq','fq_test')")" = 2 ]; }

fq_test_migrated() { [ "$(docker compose exec -T db psql -U fq -d fq_test -tA \
  -c "SELECT to_regclass('alembic_version') IS NOT NULL AND to_regclass('procrastinate_jobs') IS NOT NULL")" = t ]; }

cleanup() { psql_owner -c "DROP TABLE IF EXISTS $probe" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "== /healthz"
curl -sS -i "http://127.0.0.1:${api_port}/healthz" | sed -n '1p;$p'
echo
check "/healthz returns 200" curl -fsS "http://127.0.0.1:${api_port}/healthz"

echo "== grafana datasource fq-postgres"
grafana_get "http://127.0.0.1:${grafana_port}/api/datasources/uid/fq-postgres/health" || true
echo
check "datasource health OK" datasource_ok

echo "== grafana_ro privileges (probe table in reporting schema, dropped on exit)"
psql_owner -c "CREATE TABLE $probe (id int)" -c "INSERT INTO $probe VALUES (1)" >/dev/null
check "grafana_ro can SELECT" psql_ro -c "SELECT count(*) FROM $probe"
if psql_ro -c "INSERT INTO $probe VALUES (2)" 2>&1; then
  echo "FAIL  grafana_ro INSERT was allowed"; fail=1
else
  echo "PASS  grafana_ro INSERT denied (read-only session default)"
fi
# Defence in depth: even with the session default overridden, the grants must refuse writes.
if psql_ro -c "SET default_transaction_read_only = off" \
           -c "INSERT INTO $probe VALUES (3)" 2>&1; then
  echo "FAIL  grafana_ro INSERT allowed once read-only default is overridden"; fail=1
else
  echo "PASS  grafana_ro INSERT denied by privileges"
fi

echo "== databases"
check "fq and fq_test exist" databases_exist
check "fq_test is migrated" fq_test_migrated

echo "== backend image"
size_mb=$(docker image inspect fq-backend:dev --format '{{.Size}}' | awk '{printf "%d", $1/1000000}')
user=$(docker run --rm --entrypoint id fq-backend:dev -un)
echo "size=${size_mb}MB user=${user}"
check "image under 300 MB" test "$size_mb" -lt 300
check "image runs as non-root" test "$user" != root

exit "$fail"
