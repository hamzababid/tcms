# Implementation checklist

Status per story: ✅ done (acceptance automated and passing) · 🟡 partial · ⬜ not started. Test paths are relative to `backend/tests` or `frontend/`.

## M0 — Foundations (branch `milestone/m0-foundations`)

| Story | Status | Acceptance → tests | Notes / deferred |
| --- | --- | --- | --- |
| US-001 Start the full stack with one command | ✅ | `make up && make migrate && make seed`: 66 s for a no-cache rebuild (base images cached); web :5173, api :8000, Mailpit :8025 (ports configurable). E2E `e2e/smoke.spec.ts` runs against the stack | Seed has no steps until M1 (L3). MinIO image source changed (L1) |
| US-002 Errors are problem+json with a stable code | ✅ | `api/test_problems.py`: unknown route, validation error with field pointers, every `DomainError` subclass → status + code, `request_id`, 405, 500 without leaking details; E2E unknown route | — |
| US-003 DB enforces immutability | ✅ | `integration/test_immutability.py` (`test_br_06_final_result_immutable_sql`, `test_br_01_version_content_immutable_sql`, `test_br_01_approval_columns_settable_once`, `test_br_26_audit_append_only_sql`, `test_br_07_single_draft_per_run`); `integration/test_schema.py::test_verify_sql_passes_as_app_role` (99_verify 35/35) | — |
| US-004 Jobs run with retry and dead-letter | ✅ | `integration/test_jobs.py`: backoff then `dead`, permanent `failed`, unknown type, dedupe, stale requeue, SKIP LOCKED, scheduler once per period, admin retry (TCMS-139 backend part) | Admin UI for dead jobs: M8 |
| US-005 API client generated; CI fails on drift | ✅ | `make api-client-check` (CI job `openapi-drift`); verified failing after an unregenerated schema change | — |
| US-006 Module boundaries enforced | ✅ | `lint-imports` (11 contracts); `unit/test_module_boundaries.py` proves private-model and upward imports fail | — |

M0 acceptance (docs/09):

| Criterion | Evidence |
| --- | --- |
| `make up && make migrate && make seed` < 10 min on a clean machine | 66 s measured (see L6) |
| `alembic check` clean | `integration/test_schema.py::test_alembic_check_is_clean` |
| Migrated schema matches `01_baseline.sql` | `test_migrated_schema_matches_docs_baseline` (pg_dump diff) |
| `99_verify.sql` passes as `tcms_app` in CI | `test_verify_sql_passes_as_app_role`; also run manually on the compose DB: 35/35 |
| problem+json for unknown route | `api/test_problems.py::test_unknown_route_is_problem_json`, E2E |
| Job runs and retries in a test | `integration/test_jobs.py` |

Technical milestones: TM-1 ✅ (baseline schema, triggers, grants) · TM-3 ✅ (generated client + drift check).

Also delivered (E01 technical tasks): core primitives (settings, UoW with audit/events/jobs, errors, AccessContext, permission registry, UUIDv7, clock, pagination/filter/sort allow-lists, row_version, scoping), ORM models for all 50 tables, audit recorder, worker + scheduler + jobs retention, S3 storage primitives, health live/ready, CLI (`migrate`, `worker`, `seed`, `storage-init`, `openapi`), frontend shell, `StatusBadge`/`ProgressBar`/`Metric`, CI gates, BR manifest, coverage gate, Schemathesis contract test.

## M1 — Identity, access and workspace

⬜ Not started (US-010…029, US-160, plus US-161/US-164 backend per review K4).
