#!/bin/sh
# Runs once, on first start of an empty pgdata volume (`make reset-db` recreates it).
# Creates the test database and the read-only Grafana role. POSTGRES_USER owns database `fq`.
set -eu

psql -v ON_ERROR_STOP=1 -v ro_password="$GRAFANA_RO_PASSWORD" -v owner="$POSTGRES_USER" \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE DATABASE fq_test OWNER :"owner";

CREATE ROLE grafana_ro LOGIN PASSWORD :'ro_password';
ALTER ROLE grafana_ro SET default_transaction_read_only = on;

REVOKE CONNECT, TEMPORARY ON DATABASE fq FROM PUBLIC;
REVOKE CONNECT ON DATABASE fq_test FROM PUBLIC;
GRANT CONNECT ON DATABASE fq TO grafana_ro;

-- Grafana reads the reporting.* views only (architecture §12); the schema is owned here
-- so the grants exist before the first migration creates anything in it.
CREATE SCHEMA reporting AUTHORIZATION :"owner";
GRANT USAGE ON SCHEMA reporting TO grafana_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA reporting GRANT SELECT ON TABLES TO grafana_ro;

-- fq_test is migrated with the same migrations, so it needs the schema too. No Grafana grants:
-- grafana_ro cannot connect to it.
\connect fq_test
CREATE SCHEMA reporting AUTHORIZATION :"owner";
SQL
