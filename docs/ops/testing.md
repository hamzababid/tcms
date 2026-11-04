# Testing

Strategy and gates: docs/08. This page describes how the suites are wired.

## Backend (`backend/tests`)

| Folder | Level | Needs |
| --- | --- | --- |
| `unit/` | Pure functions (rules, pagination, permissions, formatting) | nothing |
| `integration/` | Services/SQL against a real database: schema, immutability, UoW/audit, jobs, storage | Docker |
| `api/` | HTTP behaviour through FastAPI's TestClient | Docker for some |
| `contract/` | Schemathesis: every documented operation conforms to the OpenAPI document | Docker |
| `test_rule_coverage.py` | BR traceability gate (see below) | nothing |

- `tests/conftest.py` starts **one PostgreSQL 16 container per pytest-xdist worker** and initialises it like a deployment: `00_roles.sql`, then `alembic upgrade head` as `tcms_owner`. Tests connect as `tcms_app`. MinIO uses `cgr.dev/chainguard/minio` (Docker Hub no longer publishes `minio/minio`).
- `db_session` wraps a test in a transaction that is rolled back. Tests of transaction behaviour (audit, jobs) commit for real and use unique IDs, or `clean_jobs`.
- Time: use `tcms.core.clock.frozen(...)`, never wall-clock assertions.
- Run: `make test-backend` (parallel), or `cd backend && uv run pytest tests/unit -q` for the fast subset.

### Naming (docs/04 §12)

- Business rules: `test_br_XX_<description>` or `@pytest.mark.br("BR-XX")`.
- Acceptance criteria: cite the `AC-*` / `TCMS-*` IDs in the docstring.

### Gates

| Gate | Where |
| --- | --- |
| BR traceability | `tests/br_manifest.py` maps every BR in docs/01 §7 to its milestone; BRs of milestones in `COMPLETED` must have a test. Move a milestone into `COMPLETED` when its acceptance passes |
| Coverage | `scripts/coverage_gate.py`: ≥ 85% lines on `*/service.py`, `*/rules.py`, `reporting/*` (excluding models), ≥ 95% branches on `*/rules.py`. Nothing is gated until such modules exist |
| Module boundaries | `lint-imports` (layers from docs/03 §5.1; models and repositories private); `tests/unit/test_module_boundaries.py` proves violations fail |

## Frontend (`frontend`)

- Vitest + Testing Library: `src/**/*.test.tsx` (`make test-frontend`).
- Playwright + axe: `frontend/e2e` against the running stack (`make e2e`; `E2E_BASE_URL` overrides the web URL). CI fails on serious/critical axe violations.
- E2E sessions: the `setup` project (`e2e/auth.setup.ts`) signs Bilal and Sana in once and saves their sessions to `e2e/.auth/` (git-ignored); M2+ journeys reuse them so the suite stays under the public auth limit (`RATE_LIMIT_AUTH_PER_MIN`, 20/min per IP). Running the suite several times within a minute on one machine can still hit the limit (`429` / "Too many requests"): wait a minute.
- M2 journeys (`e2e/m2.spec.ts`) create their own folders, cases and (for TCMS-038) a project with approval on, named with a per-run suffix, so they don't depend on or change the seeded SPARK repository.

## CI (`.github/workflows/ci.yml`)

`lint` → `backend-tests` (coverage gate) ∥ `frontend-tests` ∥ `openapi-drift` → `images` → `e2e`. Nightly jobs (all browsers, ZAP, perf, restore smoke) are added in the milestones that give them content (M8).
