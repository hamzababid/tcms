#!/bin/sh
# Restore the production stack from a backup (US-181, TCMS-141, docs/ops/deploy.md §Restore).
#   deploy/restore.sh backups/daily/tcms-20261108T011500Z.dump [--yes]
# Replaces the database tcms with the dump and uploads the objects the bucket is missing. The roles
# (tcms_owner, tcms_app, tcms_readonly) and deploy/secrets/ must be those of the backed-up installation.
set -eu
cd "$(dirname "$0")"
ENV_FILE=${ENV_FILE:-prod.env}
COMPOSE_FILES=${COMPOSE_FILES:--f docker-compose.prod.yml}
# shellcheck disable=SC2086
compose() { docker compose $COMPOSE_FILES --env-file "$ENV_FILE" "$@"; }

dump=${1:?usage: restore.sh DUMP_FILE [--yes]}
[ -f "$dump" ] || { echo "no such dump: $dump" >&2; exit 1; }
if [ -f "$dump.sha256" ]; then
  (cd "$(dirname "$dump")" && { sha256sum -c "$(basename "$dump").sha256" 2>/dev/null \
    || shasum -a 256 -c "$(basename "$dump").sha256"; }) > /dev/null
fi
dir=$(grep -E '^TCMS_BACKUP_DIR=' "$ENV_FILE" | tail -1 | cut -d= -f2-)
dir=${dir:-./backups}
if [ "${2:-}" != "--yes" ]; then
  printf 'This replaces ALL data in the database tcms with %s. Type RESTORE to continue: ' "$dump"
  read -r answer
  [ "$answer" = "RESTORE" ] || { echo "cancelled"; exit 1; }
fi

started=$(date +%s)
echo "$(date -u +%FT%TZ) restore: stopping the application"
compose stop caddy api worker
compose up -d db minio
until compose exec -T db pg_isready -U postgres -d postgres > /dev/null 2>&1; do sleep 1; done

echo "$(date -u +%FT%TZ) restore: database ← $dump"
compose exec -T db psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'tcms' AND pid <> pg_backend_pid()" \
  -c "DROP DATABASE IF EXISTS tcms" -c "CREATE DATABASE tcms OWNER tcms_owner"
compose exec -T db pg_restore -U postgres -d tcms --exit-on-error < "$dump"

echo "$(date -u +%FT%TZ) restore: objects ← $dir/objects"
compose run --rm --no-deps storage-init
compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$(cd "$dir" && pwd)/objects:/backup/objects:ro" \
  api tcms storage-restore /backup/objects

echo "$(date -u +%FT%TZ) restore: starting (migrations run first)"
compose up -d
until compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/ready')" > /dev/null 2>&1; do sleep 2; done

echo "$(date -u +%FT%TZ) restore: integrity checks"
compose exec -T db sh -c 'PGPASSWORD="$(cat /run/secrets/db_app_password)" psql -h localhost -U tcms_app -d tcms -v ON_ERROR_STOP=1' \
  < integrity.sql | tee /tmp/assay-integrity.txt
if grep -qE '\| f +\|' /tmp/assay-integrity.txt; then
  echo "restore: an integrity check failed" >&2
  exit 1
fi
echo "$(date -u +%FT%TZ) restore: done in $(( $(date +%s) - started )) s"
