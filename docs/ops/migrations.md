# Database migrations

Rules from docs/05 §8 and ADR-014, plus what M0 established.

## How it works

- Alembic lives in `backend/migrations`; `tcms migrate` (= `make migrate`) runs `alembic upgrade head`.
- Migrations always run as **`tcms_owner`** (`DATABASE_MAINTENANCE_URL`). `env.py` refuses any other role.
- `0001_baseline` executes `docs/schema/01_baseline.sql` and `docs/schema/02_seed_system.sql` verbatim. Only their own outer `BEGIN;`/`COMMIT;` lines are dropped, because Alembic owns the transaction. **Those two files are frozen**: later schema changes go into new migrations plus a new `docs/schema/NN_<slug>.sql` file, so the docs keep an executable form.
- File names: `YYYYMMDD_HHMM_<slug>.py`. Forward-only: `downgrade()` raises.

## Writing a migration

1. Update `docs/05-Database-Design.md` (storage owner) and add/extend `docs/schema/NN_<slug>.sql`.
2. Change the ORM models in the owning module.
3. `cd backend && ALEMBIC_DATABASE_URL=... uv run alembic revision -m "<slug>"`, then hand-write the upgrade. Autogenerate is only a draft (docs/05 §8.1).
4. **Every new table needs grants:** call `grant_app("<table>")` (or `append_only=True`). The baseline granted privileges only on tables that existed at that time; there are no default privileges (review G7). `tests/integration/test_schema.py::test_app_role_privileges` fails otherwise.
5. Enum additions (`ALTER TYPE … ADD VALUE`) go in their own migration.
6. Large backfills run as batched jobs, never inside the migration transaction.

## Checks (CI and `make schema-check`)

| Check | Guards |
| --- | --- |
| `test_alembic_check_is_clean` | ORM models match the migrated schema (`alembic check`) |
| `test_migrated_schema_matches_docs_baseline` | `pg_dump --schema-only` of the migrated DB equals a DB built from `docs/schema` (catches triggers, functions, CHECK constraints and expression indexes that Alembic cannot compare) |
| `test_verify_sql_passes_as_app_role` | `docs/schema/99_verify.sql`, 35 invariant checks, as `tcms_app` |
| `test_app_role_privileges` | `tcms_app` privileges per table (append-only tables: SELECT/INSERT only) |
| `test_seeded_role_permissions_match_code_registry` | `02_seed_system.sql` equals `tcms.core.permissions.ROLE_PERMISSIONS` |

Expression and operator-class indexes are excluded from `alembic check` (`SQL_ONLY_INDEXES` in `env.py`). They are covered by the schema diff.

## Production upgrade

Pull images → run the `migrate` container (`tcms migrate`) → rolling restart of api and worker. Migrations must be backward compatible (expand → migrate → contract). The production pipeline is TM-8 (M8).
