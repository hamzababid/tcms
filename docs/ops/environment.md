# Environment variables

The backend reads its configuration from the environment (`tcms.core.config.Settings`, docs/03 §16). Names are case-insensitive. Local values live in `.env` (from `.env.example`) and are passed in by `docker-compose.yml`.

## Backend (api, worker, migrate, CLI)

| Variable | Default | Purpose |
| --- | --- | --- |
| `TCMS_ENV` | `local` | `local`, `test`, `staging`, `production`. Production disables `/api/v1/docs` and seeding |
| `TCMS_PRODUCT_NAME` | `Assay` | Product name used by the API title and (from M1) emails |
| `TCMS_BASE_URL` | `http://localhost:5173` | Public origin: links in emails, CSRF origin check (M1) |
| `TCMS_SECRET_KEY` | — | ≥ 32 characters. Keys the recovery-code HMAC. `make env` generates a local value |
| `TCMS_ENCRYPTION_KEYS` | — | `k1:base64(32 bytes)[,k0:oldkey]` AES-256-GCM key ring for TOTP secrets and MFA setup tokens; the first key encrypts, all decrypt (rotation). `make env` generates a local value |
| `DATABASE_URL` | — | App connection as `tcms_app` |
| `DATABASE_MAINTENANCE_URL` | — | Migrations and maintenance as `tcms_owner`. The worker also needs it: the daily audit retention purge (`audit.retention`, M8b) deletes as this role |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `10` | SQLAlchemy pool per process |
| `DB_STATEMENT_TIMEOUT_MS_API` / `_WORKER` | `15000` / `300000` | PostgreSQL `statement_timeout` (docs/03 §14) |
| `S3_ENDPOINT_URL` | — | Empty for AWS S3; `http://minio:9000` locally |
| `S3_BUCKET` | `tcms-attachments` | Attachments bucket (`tcms storage-init` creates it locally) |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` / `S3_REGION` | — / — / `us-east-1` | Object storage credentials |
| `ATTACHMENTS_PRESIGNED_DOWNLOADS` | `false` | 302 to presigned URLs for downloads (M2) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | `localhost`, `1025`, …, `Assay <no-reply@localhost>`, `false` | Email (M1) |
| `WORKER_CONCURRENCY` | `4` | Job threads per worker container |
| `WORKER_POLL_INTERVAL_SECONDS` | `1.0` | Idle poll interval |
| `LOG_LEVEL` | `INFO` | JSON logs to stdout |
| `SESSION_COOKIE_SECURE` | `true` | `false` only for local http |
| `RATE_LIMIT_AUTH_PER_MIN` | `20` | Public auth endpoints per client IP per minute (`auth_rate_limits` table) |
| `FEATURE_FLAGS` | empty | Phase 2 gates |
| `MIGRATIONS_PATH` | `backend/migrations` | Where Alembic scripts live (the image keeps the repository layout) |
| `ALEMBIC_DATABASE_URL` | — | Overrides `DATABASE_MAINTENANCE_URL` for a single Alembic run (used by tests) |

## Frontend (build time)

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_PRODUCT_NAME` | `Assay` | Product name in the UI; keep equal to `TCMS_PRODUCT_NAME` |
| `VITE_API_PROXY_TARGET` | `http://localhost:8000` | Dev server proxy for `/api` |

## docker-compose only

| Variable | Purpose |
| --- | --- |
| `TCMS_WEB_PORT`, `TCMS_API_PORT`, `TCMS_DB_PORT`, `TCMS_MAILPIT_PORT`, `TCMS_MINIO_PORT`, `TCMS_MINIO_CONSOLE_PORT` | Host ports |
| `POSTGRES_PASSWORD` | Superuser password of the local db container |
| `TCMS_DB_OWNER_PASSWORD`, `TCMS_DB_APP_PASSWORD`, `TCMS_DB_READONLY_PASSWORD` | Role passwords set by `ops/db/init-roles.sh` on the first start of the db volume |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | Local MinIO credentials (also used as S3 keys) |
