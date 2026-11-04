# 11 — Decision Log (Architecture and Product Decision Records)

| Field | Value |
| --- | --- |
| Version | 1.0 · 2026-11-03 |
| Rule | A change to any decision below requires a new ADR that supersedes it; code must not silently deviate |

Status values: **Accepted**, **Superseded by ADR-xxx**, **Proposed**.

---

## ADR-001 — Modular monolith

- **Status:** Accepted
- **Context:** Two maintainers, generated code, modest scale; the brief asks to avoid unnecessary microservices.
- **Decision:** One backend codebase and image with domain packages (identity, workspace, testdesign, planning, execution, defects, requirements, reporting, integrations, platform), enforced boundaries (import-linter), in-process events, one database.
- **Consequences:** Simple deployment, transactions across modules where needed, easy refactoring. Risk of boundary erosion mitigated by CI contracts. A module can be extracted later behind its service interface.
- **Alternatives:** Microservices (rejected: operational overhead, distributed transactions); unstructured monolith (rejected: maintainability).

## ADR-002 — Technology stack

- **Status:** Accepted
- **Context:** Brief prefers React/TypeScript, FastAPI, PostgreSQL.
- **Decision:** Keep the preferred stack: React 18 + TS + Vite + Tailwind + shadcn/ui + TanStack; Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2; PostgreSQL 16.
- **Consequences:** Strong typing end to end via OpenAPI; large ecosystem; Claude Code is effective with it.
- **Alternatives:** Django + DRF (strong admin/ORM but less natural for typed OpenAPI-first APIs); NestJS (one language, but brief prefers Python).

## ADR-003 — Multi-tenancy: shared schema, application-enforced scoping, no RLS in MVP

- **Status:** Accepted
- **Context:** Internal-first but SaaS-ready; 1–5 organizations in year 1.
- **Decision:** `organization_id` (and `project_id`) on all tenant-owned rows; scoped repository base requiring an `AccessContext`; cross-tenant tests for every endpoint. PostgreSQL RLS deferred.
- **Consequences:** Simple pooling and debugging; correctness relies on code discipline + tests. Moving to RLS later is additive (policies on existing columns).
- **Alternatives:** RLS now (more defence in depth, more complexity); schema per tenant (operationally heavy).

## ADR-004 — Synchronous SQLAlchemy and sync route handlers

- **Status:** Accepted
- **Context:** Throughput needs are low; async adds complexity (session handling, testing, library compatibility).
- **Decision:** `def` handlers executed in FastAPI's thread pool; SQLAlchemy 2.0 sync with psycopg 3.
- **Consequences:** Simpler code and tests; adequate for 50 concurrent testers. If needed later, hot paths can move to async without changing contracts.
- **Alternatives:** Fully async stack.

## ADR-005 — Background jobs in PostgreSQL (no Redis in MVP)

- **Status:** Accepted
- **Context:** Need retries, scheduling and a transactional outbox for integrations; want minimal moving parts.
- **Decision:** `jobs` table with `FOR UPDATE SKIP LOCKED` workers, scheduler loop, dedupe keys, backoff, dead-letter. Jobs inserted in the same transaction as the business change (outbox).
- **Consequences:** No message broker to operate; exactly-once enqueue relative to business data; throughput sufficient (hundreds of jobs/min). Trigger to revisit: sustained > 50 jobs/s or need for pub/sub.
- **Alternatives:** Celery/RQ/arq + Redis (extra infrastructure, dual-write problem); Procrastinate (viable library; in-house chosen for transparency and outbox integration — swap allowed via ADR if maintenance cost grows).

## ADR-006 — Server-side sessions with CSRF; opaque API tokens

- **Status:** Accepted
- **Context:** Browser SPA on the same origin; compliance needs immediate revocation.
- **Decision:** Opaque session token in HttpOnly cookie, hashed in `sessions` table; double-submit CSRF; personal API tokens (opaque, hashed) for automation and scripts. No JWTs.
- **Consequences:** Revocation is immediate; one DB lookup per request (cheap, indexed). Same-origin deployment required (reverse proxy).
- **Alternatives:** JWT access/refresh (harder revocation, more client complexity).

## ADR-007 — Immutability enforced in the database

- **Status:** Accepted
- **Context:** Results, versions and audit must be tamper-resistant for trust and ISO 27001/SOC 2.
- **Decision:** Triggers block UPDATE/DELETE on immutable rows (final results, step results of final results, versions/steps, append-only tables); app role lacks UPDATE/DELETE on append-only tables; purge only via a SECURITY DEFINER function with rule checks.
- **Consequences:** Bugs cannot silently rewrite history; maintenance operations need the owner role.
- **Alternatives:** Application-only enforcement (weaker).

## ADR-008 — Audit events in the same transaction, append-only table

- **Status:** Accepted
- **Decision:** Services call `uow.audit(...)`; events inserted before commit; P2 adds a hash chain.
- **Consequences:** No missing audit for committed changes; no audit for rolled-back ones. Audit volume grows linearly; indexes and future partitioning planned (ADR-016).
- **Alternatives:** Async audit via queue (risk of loss); DB triggers generating audit (lose actor/context semantics).

## ADR-009 — UUIDv7 primary keys plus human-readable per-project keys

- **Status:** Accepted
- **Decision:** UUIDv7 generated in the app for all PKs; `key_sequences` allocate `PROJECT-PREFIX-n` keys, never reused, never changed.
- **Consequences:** Good index locality, safe to expose IDs, merge-friendly; readable keys for humans and Jira-like references.
- **Alternatives:** bigserial IDs (enumeration risk, tenant merge issues); random UUIDv4 (index bloat).

## ADR-010 — Environment-based configuration, S3-compatible storage, Docker

- **Status:** Accepted
- **Decision:** 12-factor configuration; attachments in any S3-compatible store (MinIO locally); images built in CI; Compose for local and reference production.
- **Consequences:** Portable between on-prem and cloud.

## ADR-011 — Connector architecture with single ownership per field

- **Status:** Accepted
- **Context:** Jira is used; brief forbids uncontrolled bidirectional sync.
- **Decision:** Connector protocol + registry; `external_links` with `owner`; outbound via jobs (outbox), inbound via webhook + polling into mirror fields only. Each field has exactly one owner (HLD §8.3).
- **Consequences:** No sync conflicts by construction; some fields read-only in TCMS for Jira-owned records.
- **Alternatives:** Full bidirectional sync with conflict resolution (complex, error-prone).

## ADR-012 — Test classification model; no test-case severity; folder as module

- **Status:** Accepted
- **Context:** The brief's classification list mixes *what* is tested (API, UI, security), *how* cases were designed (positive, negative, boundary) and *suite membership* (smoke, sanity, regression).
- **Decision:** `type` (single), `design_technique` (optional single), system tags `smoke`/`sanity`/`regression`. Case "severity" dropped (priority + defect severity suffice). "Module/Feature" = folder at configurable depth for reporting.
- **Consequences:** Cleaner filters and reports; one case can be in regression and smoke at once via tags.
- **Alternatives:** One multi-select "classification" (ambiguous reporting).

## ADR-013 — Single metric-definitions module; honest rates

- **Status:** Accepted
- **Decision:** All metrics defined once in `reporting/metrics.py`; rates return `null` when denominators are 0; every rate is exposed with numerator and denominator; superseded runs excluded; N/A excluded from denominators but shown; no "Passed with exceptions" status — skipped steps are flagged.
- **Consequences:** Consistent numbers across dashboards, exports and readiness; tests compare against an oracle.

## ADR-014 — Forward-only migrations with expand/contract

- **Status:** Accepted
- **Decision:** Alembic; reviewed migrations; no production downgrades; breaking schema changes done over two releases.
- **Consequences:** Zero-downtime-friendly upgrades; rollbacks are done by forward fixes or restore.

## ADR-015 — Markdown text fields, not WYSIWYG

- **Status:** Accepted
- **Decision:** Markdown (CommonMark + tables) with toolbar and preview, sanitized rendering, pasted images as attachments.
- **Consequences:** Simple, diff-friendly (version compare), safe; testers familiar with Jira markup adapt quickly. A WYSIWYG editor can be layered later producing the same Markdown.

## ADR-016 — Defer partitioning

- **Status:** Accepted
- **Decision:** Regular tables for `audit_events` and `test_results` until > 50 M rows; then monthly range partitions via a planned migration.
- **Consequences:** Simpler MVP; plan exists for growth.

## ADR-017 — Draft/final attempt model for execution

- **Status:** Accepted
- **Context:** Testers change their minds while executing; history must be immutable once recorded.
- **Decision:** Each execution is an attempt: draft (mutable, by executor) → final (immutable). Retest and correction add attempts. Run status = latest final attempt.
- **Consequences:** Natural editing during execution and strict history afterwards; requires discard semantics for abandoned drafts.
- **Alternatives:** Overwrite run status (loses history); every step click immutable (unusable).

## ADR-018 — Version pinning with eligibility rule

- **Status:** Accepted
- **Decision:** Runs pin a version at creation: approved version when approval is enforced, else latest. "Update to latest" only without attempts; otherwise "Replace run" (supersede).
- **Consequences:** Results always describe what was executed; testers see a banner for newer versions.

## ADR-019 — One home folder per case

- **Status:** Accepted
- **Decision:** Cases live in exactly one folder; cross-cutting groupings via tags, saved filters and plans.
- **Consequences:** Unambiguous moves, counts and permissions. Users wanting "a case in two suites" use tags/plans.
- **Alternatives:** Multi-parent suites (TestLink/Azure-like complexity).

## ADR-020 — Re-prioritization: Jira connector at the start of Phase 2; MFA in MVP

- **Status:** Accepted — confirmed by the product owner on 2026-11-04
- **Context:** Developers and PMs already use Jira; ISO 27001/SOC 2 evidence needs MFA.
- **Decision:** Narrow Jira connector is the first Phase 2 item (brief had it in Phase 3). TOTP MFA moves into the MVP. Jira remains architecturally supported from MVP (tables reserved, connector protocol defined, outbox in place).
- **Consequences:** Avoids defect double-entry early; slightly larger MVP auth scope.

## ADR-021 — Offset pagination with totals

- **Status:** Accepted
- **Decision:** `page`/`page_size` (max 200) with `total` for UI tables; exports for bulk data.
- **Consequences:** Simple UI (page numbers, "select all N matching"); acceptable cost at expected volumes with indexed sorts. Cursor pagination can be added for automation APIs if needed.

## ADR-022 — PostgreSQL full-text and trigram search

- **Status:** Accepted
- **Decision:** `tsvector` + GIN and `pg_trgm` for global and list search; no external search engine.
- **Consequences:** No extra infrastructure; adequate up to ~1 M searchable records. Revisit with OpenSearch fed by the outbox if needed.
