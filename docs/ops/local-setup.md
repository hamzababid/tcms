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
make seed      # demo data; M0 registers no seed steps yet, M1 adds org, users and SPARK
```

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

## Resetting

```bash
docker compose down -v   # removes the database and object-storage volumes
make up
```
