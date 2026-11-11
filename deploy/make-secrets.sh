#!/bin/sh
# Create deploy/secrets/* with random values for a new installation (docs/ops/deploy.md). Existing files
# are kept, so re-running never changes a password a running database already uses.
# Permissions: the directory is 0700 (only the host admin can open it); the files are 0644, because Compose
# bind-mounts them as they are and the containers read them as their own non-root users, which a 0600
# file owned by the admin would refuse (seen on Linux; Docker Desktop on macOS hides it).
# Usage: deploy/make-secrets.sh [smtp-password]
set -eu
cd "$(dirname "$0")"
umask 077
mkdir -p secrets
chmod 700 secrets

rand() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-40; }
put() { [ -s "secrets/$1" ] || printf '%s' "$2" > "secrets/$1"; }

put postgres_password "$(rand)"
put db_owner_password "$(rand)"
put db_app_password "$(rand)"
put db_readonly_password "$(rand)"
put s3_secret_access_key "$(rand)"
put smtp_password "${1:-}"
put tcms_secret_key "$(openssl rand -base64 48 | tr -d '\n')"
put tcms_encryption_keys "k1:$(openssl rand -base64 32 | tr -d '\n')"
# The application connects with the passwords above.
put database_url "postgresql+psycopg://tcms_app:$(cat secrets/db_app_password)@db:5432/tcms"
put database_maintenance_url "postgresql+psycopg://tcms_owner:$(cat secrets/db_owner_password)@db:5432/tcms"

chmod 644 secrets/*
echo "secrets in $(pwd)/secrets:"
ls secrets
