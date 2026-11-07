# M7 — Reporting, readiness and notifications · Tasks

Order per CLAUDE.md §4: docs, tests first, rules → migration → service → schemas → router → authz →
client → frontend → E2E → close-out. Q1 = a (D1) and Q2 = a (D17), answered 2026-11-06. This branch is M7a (sections 0–3, 5); M7b (section 4) follows.

## 0. Docs
- [x] 0.1 docs/02 §11 (AC-RPT/REL/NTF, rule semantics D2, readiness scope D1, report columns D9), §2.7 (events, email, opt-outs); docs/04 §8 (queries module, snapshot counters, readiness, export), §10.4; docs/06 §4.1, §4.3, §4.10, §4.13, §5.9; docs/07 §5.2, §5.3, §5.12, §5.15 (defect leftovers → bug links), bell; docs/08 §15; docs/09 M7 row; docs/10 E13/E16; ADR-025 if Q1 changes docs/02 meaning.

## 1. Metrics and readiness (M7a)
- [x] 1.1 Unit tests + metrics additions; `reporting/queries.py` filtered counts; property test vs oracle (TCMS-113/114, BR-24).
- [x] 1.2 `reporting/readiness.py` (rules, defaults, D1 merge) + unit tests; plan and release readiness endpoints.
- [x] 1.3 Decisions service + endpoints (append-only, snapshot, audit) (TCMS-116).
- [x] 1.4 Snapshot job + refresh endpoint; counters per D5.

## 2. Dashboards and reports (M7a)
- [x] 2.1 Manager dashboard, quality dashboard, org dashboard, My Work additions (endpoints + schemas).
- [x] 2.2 Report declarations (6) with filters and pagination.
- [x] 2.3 Export: CSV/XLSX writers with escaping (TCMS-117), sync path, `export.generate` job, data transfers endpoints, purge.
- [x] 2.4 Authz matrix, BR manifest (BR-24 → M7), api-client.

## 3. Frontend (M7a)
- [x] 3.1 Chart components + data tables.
- [x] 3.2 Overview page (`/p/:key`, `G O`) with filters; My Work widgets; org dashboard (`/org`).
- [x] 3.3 Releases list + release page (Readiness, Plans, Cycles, Bugs, Decisions) + decision dialog; plan Overview readiness.
- [x] 3.4 Reports pages (Quality dashboard + six reports with export).

## 4. Notifications and email (M7b)
- [x] 4.1 Notifications API, renderers, new events (retest, export ready), cleanup job.
- [x] 4.2 Preferences, mention email, digest job, templates.
- [x] 4.3 Bell, notification list, Profile › Notifications.

## 5. Performance
- [x] 5.1 `large` seed profile (TM-4, 2× year one, L43); measure and log in `docs/ops/performance.md`.

## 6. E2E and close-out
- [x] 6.1 `frontend/e2e/m7.spec.ts` (UJ-8, Overview, export, My Work); `m7b.spec.ts` (bell, opt-out).
- [x] 6.2 Seed (SPARK decision, snapshots for 15 days); all gates; CHECKLIST; known limitations (closed L25, L26, matrix part of L38; L15, L16, L20, L33 close in M7b); local-setup.
- [x] 6.3 Commit, push, PR(s); CI green; report.
