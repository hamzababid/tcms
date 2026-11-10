#!/bin/sh
# Nightly backup of the production stack (US-181, NFR-REL-03, docs/ops/deploy.md §Backups).
#   - PostgreSQL: `pg_dump -Fc` of database tcms, checked with `pg_restore --list`
#   - Object storage: every object not yet in the copy (objects never change after upload)
#   - Retention: 30 daily dumps; the first dump of each month is also kept as a monthly (12 kept)
# Run from cron on the host, e.g. `15 1 * * * /opt/assay/deploy/backup.sh >> /var/log/assay-backup.log 2>&1`.
# Copy the backup directory off the host (and keep deploy/secrets/ in a separate safe place: the encryption
# keys are needed to read two-step verification secrets after a restore).
set -eu
cd "$(dirname "$0")"
ENV_FILE=${ENV_FILE:-prod.env}
COMPOSE_FILES=${COMPOSE_FILES:--f docker-compose.prod.yml}
# shellcheck disable=SC2086
compose() { docker compose $COMPOSE_FILES --env-file "$ENV_FILE" "$@"; }

dir=$(grep -E '^TCMS_BACKUP_DIR=' "$ENV_FILE" | tail -1 | cut -d= -f2-)
dir=${dir:-./backups}
mkdir -p "$dir/daily" "$dir/monthly" "$dir/objects"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
dump="$dir/daily/tcms-$stamp.dump"

echo "$(date -u +%FT%TZ) backup: database → $dump"
compose exec -T db pg_dump -U postgres -Fc --no-password tcms > "$dump.part"
compose exec -T db pg_restore --list < "$dump.part" > /dev/null   # a readable archive or the script stops
mv "$dump.part" "$dump"
(cd "$dir/daily" && name=$(basename "$dump") \
  && { sha256sum "$name" 2>/dev/null || shasum -a 256 "$name"; } > "$name.sha256")

echo "$(date -u +%FT%TZ) backup: objects → $dir/objects"
compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$(cd "$dir" && pwd)/objects:/backup/objects" \
  api tcms storage-backup /backup/objects

if [ "$(date -u +%d)" = "01" ] || [ -z "$(ls -A "$dir/monthly")" ]; then
  cp "$dump" "$dump.sha256" "$dir/monthly/"
fi
prune() { ls -1t "$1"/*.dump 2>/dev/null | tail -n +"$(($2 + 1))" | while read -r f; do rm -f "$f" "$f.sha256"; done; }
prune "$dir/daily" 30
prune "$dir/monthly" 12

echo "$(date -u +%FT%TZ) backup: done ($(du -h "$dump" | cut -f1) database, $(du -sh "$dir/objects" | cut -f1) objects)"
