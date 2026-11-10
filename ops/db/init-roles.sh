#!/bin/sh
# PostgreSQL first-start init (docker-entrypoint-initdb.d): cluster roles from docs/schema/00_roles.sql,
# real passwords from the environment (or from *_FILE, the production stack's secrets), then the tcms
# database owned by tcms_owner.
set -eu

secret() {
  file_var="$1_FILE"
  eval "file=\${$file_var:-}"
  if [ -n "$file" ]; then cat "$file"; else eval "printf '%s' \"\${$1}\""; fi
}

OWNER_PW=$(secret TCMS_DB_OWNER_PASSWORD)
APP_PW=$(secret TCMS_DB_APP_PASSWORD)
RO_PW=$(secret TCMS_DB_READONLY_PASSWORD)

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -f /schema/00_roles.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" \
  -v owner_pw="$OWNER_PW" -v app_pw="$APP_PW" -v ro_pw="$RO_PW" <<'SQL'
ALTER ROLE tcms_owner PASSWORD :'owner_pw';
ALTER ROLE tcms_app PASSWORD :'app_pw';
ALTER ROLE tcms_readonly PASSWORD :'ro_pw';
CREATE DATABASE tcms OWNER tcms_owner;
SQL
