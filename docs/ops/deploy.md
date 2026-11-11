# Deployment runbook (US-180, US-181)

Single host, Docker Compose: `deploy/docker-compose.prod.yml` (docs/03 §12.2). Caddy terminates TLS and routes
`/api/*` to the API replicas (`API_REPLICAS`, default 2; each is one gunicorn process with one Uvicorn worker,
and Caddy sends each request to the replica with the fewest requests in flight) and everything else to the web
container (nginx serving the built SPA). The worker runs background jobs and the scheduler; `migrate` and `storage-init` run once at each start.
PostgreSQL 16 and MinIO run in the stack; for a managed database or S3, point the secrets and `S3_*` settings
at them and remove those services.

| File | Purpose |
| --- | --- |
| `deploy/docker-compose.prod.yml` | The stack. Third-party images pinned by digest (closes L1) |
| `deploy/Caddyfile` | TLS (Let's Encrypt, or Caddy's own CA for the local drill), HSTS, the SPA's CSP, security headers |
| `deploy/prod.env.example` | Non-secret settings; copy to `deploy/prod.env` |
| `deploy/make-secrets.sh` | Creates `deploy/secrets/*` (database passwords, URLs, signing and encryption keys, S3 secret) |
| `deploy/backup.sh`, `deploy/restore.sh`, `deploy/integrity.sql` | Backups, restore and the post-restore checks |
| `deploy/docker-compose.local.yml`, `deploy/local.env` | The local drill on `https://localhost` (adds Mailpit) |

Secrets are files mounted under `/run/secrets` and read through `NAME_FILE` variables (`TCMS_SECRET_KEY_FILE`,
`DATABASE_URL_FILE`, …; the PostgreSQL image reads `POSTGRES_PASSWORD_FILE`, `ops/db/init-roles.sh` the role
passwords). They never appear in `prod.env`, in the environment of a container, or in git
(`deploy/secrets/`, `deploy/backups/` and `deploy/prod.env` are ignored). `deploy/secrets/` is mode 0700 and its files 0644: the containers read the mounted files as their own non-root users, so a 0600 file would be refused on Linux. Keep the directory owned by the admin account.

## Install

Requirements: a Linux host with Docker Engine 27+ and the compose plugin, 4 vCPU / 8 GB RAM / 100 GB disk to
start (docs/01 §8.2), DNS for the host name, ports 80 and 443 open (80 is needed for the ACME challenge and
redirects to 443), outgoing SMTP.

```bash
git clone <repo> /opt/assay && cd /opt/assay
deploy/make-secrets.sh 'smtp-password'        # once; re-running keeps existing files
cp deploy/prod.env.example deploy/prod.env     # set TCMS_SITE_ADDRESS, TCMS_BASE_URL, SMTP_*
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/prod.env build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/prod.env up -d
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/prod.env ps     # api healthy, caddy up
curl -s https://assay.example.com/api/v1/health/ready                              # all checks ok
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/prod.env run --rm api \
  tcms bootstrap --org "ACME Energy" --slug acme --admin-email admin@example.com
```

`bootstrap` prints a one-time setup link (7 days). The administrator sets a password and enrols two-step
verification before anything else. Production refuses `tcms seed` and the dev TOTP secret.

Then: add the backup cron entry (below), copy `deploy/secrets/` to the organization's secret store, and
schedule the first restore drill.

What production mode changes (`TCMS_ENV=production`): the OpenAPI schema needs a signed-in session
(`/api/v1/openapi.json` answers 401 otherwise; `/api/v1/docs` is off), the API sends HSTS, session cookies are
`Secure`, seeding is refused. Every API response carries `X-Content-Type-Options`, `X-Frame-Options: DENY`,
`Content-Security-Policy: default-src 'none'`, `Referrer-Policy`, `Cache-Control: no-store` and the
`RateLimit-*` headers (600 requests per minute per session, API token or address; health checks exempt; the
limit is per API process, so the installation allows up to `API_REPLICAS` × 600). An address that sends more
than 600 rejected credentials in a minute gets `429` for new credentials until the minute ends; sessions and
tokens that worked in the last hour are not affected.
Client addresses come from Caddy's `X-Forwarded-For` (gunicorn `--forwarded-allow-ips`; only Caddy publishes
ports), so the sign-in limit and session records see the real client (closes L8). Caddy trusts no proxy and
replaces any `X-Forwarded-For` a client sends. If a load balancer sits in front of Caddy, add
`servers { trusted_proxies static <load balancer range> }` to the global block of `deploy/Caddyfile`, or every
client will appear as the load balancer.

Sizing: `API_REPLICAS=2` on the 4 vCPU host of docs/01 §8.2; the database settings `PG_SHARED_BUFFERS`,
`PG_EFFECTIVE_CACHE_SIZE`, `PG_WORK_MEM` and `PG_MAX_CONNECTIONS` are set in `prod.env` (values for an
8 GB host in `prod.env.example`). With `SMTP_STARTTLS=true` the mail server's certificate must be valid for
`SMTP_HOST`: Assay checks it. The M8c load tests ran with 8 replicas on a 12-core laptop; the 4 vCPU host is measured in
M9 (docs/ops/performance.md).

## Upgrade

```bash
cd /opt/assay
deploy/backup.sh                                   # always: a restore point from just before the upgrade
git fetch && git checkout <release-tag>
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/prod.env build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/prod.env up -d   # migrate runs first
curl -s https://assay.example.com/api/v1/health/ready
```

`api` and `worker` wait for `migrate` to finish. Migrations are forward-only and follow expand/contract
(docs/05 §8, ops/migrations.md), so the previous release's code works against the new schema for one
release.

## Rollback

1. Code only (the new release's migrations are additive, the usual case): check out the previous tag, `build`,
   `up -d`. The schema stays at the newer head; Administration › System shows "database at X, code expects Y"
   until the fix is redeployed, which is expected.
2. A migration broke data: restore the backup taken before the upgrade (below), then deploy the previous tag.
   Work done since the upgrade is lost; announce the window first.

## Backups

`deploy/backup.sh` (cron on the host, e.g. `15 1 * * * /opt/assay/deploy/backup.sh >> /var/log/assay-backup.log 2>&1`):

- `pg_dump -Fc` of database `tcms` into `backups/daily/`, checked with `pg_restore --list` and a SHA-256 file;
- every stored object not yet in `backups/objects/` (objects are written once under random keys, so the copy is
  incremental; objects deleted from the bucket stay in the copy);
- the first dump of each month is also kept in `backups/monthly/`; 30 daily and 12 monthly dumps are kept.

Copy `TCMS_BACKUP_DIR` off the host every night (restic, rsync or the provider's snapshot tool). Keep
`deploy/secrets/` separately: `tcms_encryption_keys` is needed to read two-step verification secrets after a
restore, and a backup holding its own keys is not a safe backup.

## Restore

```bash
deploy/restore.sh deploy/backups/daily/tcms-20261108T011500Z.dump     # asks you to type RESTORE
```

The script checks the SHA-256, stops Caddy, API and worker, recreates database `tcms` from the dump as the
cluster superuser (roles and grants come back with it), uploads the objects the bucket is missing, starts
the stack (migrations run first) and runs `deploy/integrity.sql` as `tcms_app`. It stops with an error if a
check fails. The roles and `deploy/secrets/` must be those of the backed-up installation.

## Local drill (M8 D3; TCMS-141)

The same stack on one machine, with Caddy's own certificate on `https://localhost` and Mailpit for mail
(`deploy/local.env` sets `TCMS_ENV=staging`, which runs the production images and settings but allows the demo
seed, so the E2E suite can serve as the smoke test). Stop the development stack first (ports 80 and 443).

```bash
deploy/make-secrets.sh
alias assay-local='docker compose -f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml --env-file deploy/local.env'
assay-local up -d --build && assay-local run --rm api tcms seed --profile dev
cd frontend && E2E_BASE_URL=https://localhost E2E_IGNORE_HTTPS_ERRORS=1 pnpm exec playwright test
cd ../deploy && export ENV_FILE=local.env COMPOSE_FILES="-f docker-compose.prod.yml -f docker-compose.local.yml"
./backup.sh
assay-local down && docker volume rm assay-prod_db-data assay-prod_minio-data && assay-local up -d
./restore.sh backups/daily/<dump> --yes        # then the E2E suite again
```

Variables exported in your shell (for example `TCMS_BASE_URL` from the development `.env`) override the env
file: unset them before running the drill.

### Drill log

| Date | Where | Result |
| --- | --- | --- |
| 2026-11-08 | Local drill (M8c), Apple Silicon, Docker Desktop | Stack up from scratch; `https://localhost` serves HSTS, the CSP and the API headers; HTTP redirects to HTTPS. E2E suite against the stack: 52 passed. Backup: 320 KB dump + 6 objects in 2 s. Volumes deleted, stack recreated empty, restore in 18 s; integrity checks all ok; counts equal before and after (69 cases, 36 results, 568 audit events, 4 attachments). E2E suite against the restored stack: 52 passed (first run after Caddy's recreate: 4 failed on `connection refused`, see note). Production mode (`TCMS_ENV=production`): health ready ok, OpenAPI 401 without a session, `/api/v1/docs` 404, `tcms seed` refused, `bootstrap` printed the setup link |
| — | Staging host | Planned for M9 (pilot), with a real domain and Let's Encrypt (M8 D3) |

Note: directly after `--force-recreate caddy`, Docker Desktop on macOS refused some connections to
`localhost:443` for a few seconds while the port forward came back; waiting until `curl -sk https://localhost/`
answers avoids it. `https://127.0.0.1` fails the TLS handshake because the local certificate is for
`localhost` only.
