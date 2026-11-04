# CLAUDE.md — Instructions for Claude Code

You are building **TCMS**, a self-hosted Test Case Management System. The full specification is in `docs/`. This file tells you how to work in this repository. Read it at the start of every session.

## 1. Read before you build

| Order | Document | Use it for |
| --- | --- | --- |
| 1 | `docs/09-Implementation-Roadmap.md` | Which milestone you are in and its exit criteria |
| 2 | `docs/10-Backlog.md` | The stories for that milestone |
| 3 | `docs/02-Functional-Specification.md` | Exact behaviour, fields, validation, errors, ACs |
| 4 | `docs/05-Database-Design.md` + `docs/schema/*.sql` | Tables, columns, constraints, triggers. The SQL is the executable baseline; the first Alembic migration reproduces `01_baseline.sql`, and `99_verify.sql` must pass |
| 5 | `docs/06-API-Specification.md` | Endpoints, schemas, error codes |
| 6 | `docs/04-LLD.md` | Code structure and templates you must follow |
| 7 | `docs/07-UI-UX-Specification.md` + `docs/design/` | Screens, components, shortcuts; `docs/design/*.dc.html` are the visual reference (match layout, tokens and states; rebuild with our components) |
| 8 | `docs/08-QA-Strategy.md` | Tests to write (TCMS-xxx), gates |
| — | `docs/01-PRD.md`, `docs/03-HLD.md`, `docs/11-Decision-Log.md`, `docs/12-Glossary.md` | Requirements IDs, architecture, decisions, terms |

**When documents disagree:** behaviour → Functional Spec wins; storage → Database Design wins; endpoint shape → API Spec wins; code structure → LLD wins. Do not guess: note the conflict in your summary and propose a fix to the docs.

## 2. Non-negotiable rules

1. **Never modify or delete a finalized result, a test case version, a step, an audit event, a defect status-history row or a release decision.** Corrections are new records. The DB enforces this; do not work around triggers.
2. **Every write goes through a module `service.py` function** that checks permission, validates via `rules.py`, writes, calls `uow.audit(...)`, and enqueues side effects as jobs — in one transaction.
3. **Every query is tenant-scoped** (`organization_id`, and `project_id` for project data) via the scoped repository helpers. Non-members get 404.
4. **Derived values are computed, never accepted from clients:** run status, coverage, metrics, readiness.
5. **Metrics come only from `reporting/metrics.py`.** Rates are `null` when the denominator is 0 and always carry numerator/denominator.
6. **Respect module boundaries** (`docs/03-HLD.md §5.2`); import-linter must pass. Other modules' repositories/models are private.
7. **Optimistic concurrency** on mutable aggregates with `row_version` (409 on mismatch).
8. **Do not add scope.** Phase 2/3 features (Jira, SSO, automation ingestion, shared steps, parameters, custom roles…) are not built in the MVP; keep their reserved interfaces only. New ideas go to the summary as suggestions.
9. **No new infrastructure** (Redis, search engines, brokers, extra services) without a new ADR approved by the maintainers.
10. **Secrets never in code, logs or fixtures** beyond the documented seed passwords and the documented dev-only seed TOTP secret (local seed only; refused when `TCMS_ENV=production`).

## 3. Stack and commands

Backend: Python 3.12, FastAPI (sync handlers), SQLAlchemy 2.0 (sync, typed), Alembic, Pydantic v2, psycopg 3, PostgreSQL 16, MinIO/S3, in-house PostgreSQL job queue.
Frontend: React 18, TypeScript strict, Vite, Tailwind + shadcn/ui, TanStack Router/Query/Table, react-hook-form + zod, Recharts, openapi-typescript client.

```
make up           # start stack
make migrate      # alembic upgrade head
make seed         # demo data (SPARK)
make test         # backend + frontend tests
make e2e          # Playwright
make lint         # ruff, mypy, import-linter, eslint, tsc
make api-client   # regenerate frontend client from OpenAPI
```

## 4. How to implement a story

1. Identify the story (`US-xxx`), its FR/BR/AC references and the TCMS-xxx test cases.
2. Write or extend tests first for each referenced BR/AC (`test_br_XX_*`, docstring cites AC IDs).
3. Implement in this order: migration (if needed) → models → repository → `rules.py` → `service.py` → schemas → router → authz-matrix entry → regenerate API client → frontend feature (hooks → components → route) → E2E test if the story has a user journey.
4. Run `make lint test`. Fix everything; do not skip or weaken tests.
5. Summarize: what changed, which ACs are covered by which tests, any doc conflicts found, any follow-ups.

## 5. Conventions (summary — full list in `docs/04-LLD.md §12`)

- Errors: raise `DomainError` subclasses with codes from `docs/06-API-Specification.md §3`.
- Time: `tcms.core.clock.now()`; IDs: `tcms.core.ids.new_id()` (UUIDv7).
- Enums defined once (Python `StrEnum` + PostgreSQL type); values lower_snake.
- Audit action names `entity.verb_past` (e.g. `test_case.version_created`).
- Frontend: server state via TanStack Query only; `StatusBadge` is the only place mapping statuses to colours/icons; every percentage displayed with counts via `Metric`.
- Conventional Commits; small PRs per story.

## 6. Milestone kick-off prompts (for the maintainers)

- "Read CLAUDE.md and docs/09 M0. Implement milestone M0 (E01) completely, including CI and the baseline migration from docs/05. Stop when M0 acceptance passes."
- "Implement M1 stories US-010…US-029 and US-160. Use the authz matrix harness for every new route."
- Continue milestone by milestone. Do not start a milestone before the previous one's acceptance criteria pass.

## 7. Open product decisions (assumptions in effect)

See `README.md` → Open items. Build with the stated assumptions; they are isolated so they can change without rework.
