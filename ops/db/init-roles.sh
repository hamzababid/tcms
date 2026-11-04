#!/bin/sh
# PostgreSQL first-start init (docker-entrypoint-initdb.d): cluster roles from docs/schema/00_roles.sql,
# real passwords from the environment, then the tcms database owned by tcms_owner.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -f /schema/00_roles.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" \
  -v owner_pw="$TCMS_DB_OWNER_PASSWORD" -v app_pw="$TCMS_DB_APP_PASSWORD" -v ro_pw="$TCMS_DB_READONLY_PASSWORD" <<'SQL'
ALTER ROLE tcms_owner PASSWORD :'owner_pw';
ALTER ROLE tcms_app PASSWORD :'app_pw';
ALTER ROLE tcms_readonly PASSWORD :'ro_pw';
CREATE DATABASE tcms OWNER tcms_owner;
SQL
