# Local setup

## Prerequisites

| Tool | Version | Install (macOS) |
| --- | --- | --- |
| Docker Engine + Compose v2 | 29+ / v2+ | Docker Desktop |
| Python | 3.12 (managed by uv) | `brew install uv` |
| Node.js | 20+ (CI uses 24) | `brew install node` |
| pnpm | 12 | `brew install pnpm` |
| libmagic | any | `brew install libmagic` (only for running backend tests outside Docker) |
| GNU make | 3.81+ | preinstalled |

## First run

```bash
make up        # creates .env from .env.example, builds images, starts db, minio, mailpit, migrate, api, worker, web
make migrate   # alembic upgrade head as tcms_owner (also run automatically by `make up`)
make seed      # demo data: ACME Energy, one user per role, project SPARK (idempotent)
```

`make env` (run by `make up`) creates `.env` from `.env.example` and generates random local `TCMS_SECRET_KEY` and `TCMS_ENCRYPTION_KEYS`.

## Seed accounts (local and CI stacks only)

All seed users share the password **`Passw0rd!Passw0rd`**. They exist only where `make seed` ran: never seed a shared environment.

| User | Email | Role in SPARK | MFA |
| --- | --- | --- | --- |
| Zain Ali | zain@acme.test | Org Admin (+ QA Manager, as project creator) | **Required.** Pre-enrolled with the dev-only TOTP secret `ASSAYLOCALDEVTOTPSECRETONLY23456` (add it to any authenticator app). Refused when `TCMS_ENV=production` |
| Ayesha Raza | ayesha@acme.test | QA Manager | off |
| Bilal Khan | bilal@acme.test | QA Lead | off |
| Sana Malik | sana@acme.test | QA Engineer | off |
| Omar Farooq | omar@acme.test | Developer | off |
| Hira Siddiqui | hira@acme.test | PM / BA | off |
| Faisal Ahmed | faisal@acme.test | Viewer | off |

The `dev` profile also fills the SPARK repository: 8 folders (Web Application › Authentication › Login / Password Reset, Dashboard, Backend Services › Meter Readings API, Data Integration) and 11 test cases; SPARK-TC-1 has two versions to show Versions and Compare. It also creates plan **SPARK-PL-1** (draft, every SPARK case, with exit rules) and cycle **SPARK-CY-1** (active, built from that plan, every run assigned to Sana) so Plans and Cycles have something to open. Sana has already executed part of SPARK-CY-1: 7 finished results (passed, failed, blocked, not applicable) and 1 draft, so the cycle progress, run history and My Work show real data. Sign in as Sana to continue the draft in the runner. SPARK tracks bugs in Jira (Project settings › Options › Bug tracker): `SPK-431` is linked to the failed SPARK-CY-1 result and `SPK-440` to a case, so the runner, cycle, case and Bugs pages show bug links. SPARK's stories also live in Jira: requirement references `SPK-101`…`SPK-104` are linked to SPARK cases and `SPK-105` has no case; all five are listed on SPARK-PL-1, so Requirements and Traceability have data, including one not-covered row. Ayesha has recorded a No-go for SPARK v2.5 (Releases page) and the Quality dashboard has 15 days of snapshots. For dashboard timings, `tcms seed --profile large` loads a bigger SPARK into an empty database (see docs/ops/performance.md). `tcms seed --profile e2e` also creates project HELIOS with the same team. Seed invitations are delivered to Mailpit.

Zain's sidebar has **Administration** (users, roles, audit log, access review, system status). The dev seed adds one failed job (`seed.example`) so System › Failed jobs has something to retry; it fails again at once because the type has no handler. The worker runs the daily audit retention purge with `DATABASE_MAINTENANCE_URL` (already set in `docker-compose.yml`). The Playwright setup signs Zain in once (`e2e/.auth/zain.json`) so specs do not reuse the same TOTP code.

## First organization on a real deployment

```bash
docker compose run --rm api tcms bootstrap --org "ACME Energy" --slug acme --admin-email admin@example.com
```

This prints a one-time setup link (7 days). The admin sets a password, then must enrol two-step verification before anything else.

| Service | URL (defaults) |
| --- | --- |
| Web (Vite dev server) | http://localhost:5173 |
| API | http://localhost:8000/api/v1 (OpenAPI UI at `/api/v1/docs` outside production) |
| Mailpit (captured email) | http://localhost:8025 |
| MinIO console | http://localhost:9001 |
| PostgreSQL | `localhost:5433`, database `tcms` (roles `tcms_owner`, `tcms_app`, `tcms_readonly`) |

**Port clashes.** Every published port is set in `.env` (`TCMS_WEB_PORT`, `TCMS_API_PORT`, `TCMS_DB_PORT`, …). If another stack already uses 5173, set `TCMS_WEB_PORT=5174` and `TCMS_BASE_URL=http://localhost:5174`.

**Measured (M0, Apple Silicon):** a no-cache rebuild of the project images plus `make up && make migrate && make seed` took 66 s. That figure excludes the first pull of the base images (`postgres:16`, `python:3.12-slim`, `node:24-alpine`, Chainguard MinIO, Mailpit), which depends on network speed.

## Everyday commands

| Command | Does |
| --- | --- |
| `make up` / `make down` | Start / stop (data volumes kept; `docker compose down -v` wipes them) |
| `make logs` | Follow all logs |
| `make test` | Backend pytest (testcontainers: starts its own PostgreSQL 16 and MinIO) + frontend Vitest |
| `make e2e` | Playwright + axe against the running stack |
| `make lint` | ruff, ruff format, mypy (strict), import-linter, ESLint, tsc, Prettier |
| `make api-client` | Export `backend/openapi.json` and regenerate `frontend/src/api/schema.d.ts` |
| `make api-client-check` | Fails if the committed client differs from the generated one |
| `make schema-check` | Migrated schema == `docs/schema` baseline; `alembic check`; `99_verify.sql` as `tcms_app` |

Source code is bind-mounted: the API reloads on backend changes and Vite hot-reloads the frontend.
The worker does not reload: after changing job handlers (imports, exports, notifications) run
`docker compose restart worker`. After pulling a branch with a new migration (M8a adds
`0005_m8_import_mappings`) run `docker compose run --rm migrate`.

To try an import locally, sign in as Ayesha, open a project's Repository and choose **Import**; any
export from **Export** re-imports as a no-op. The import timing test runs with
`uv run pytest -m timing tests/api/test_imports.py` (about 45 s).

## Resetting

```bash
docker compose down -v   # removes the database and object-storage volumes
make up
```
