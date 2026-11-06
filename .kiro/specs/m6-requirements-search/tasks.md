# M6 — Requirement references, traceability and search · Tasks

Order per CLAUDE.md §4: docs, tests first, rules → migration → service → schemas → router → authz →
client → frontend → E2E → close-out. Q1 = a (D3) and Q2 = a (D4), answered 2026-11-06.

## 0. Docs
- [x] 0.1 ADR-024 in docs/11; docs/01 FR-REQ, UJ-7, AS-03; docs/02 §10 (references, scope, coverage), §12; docs/05 + `docs/schema/05_m6_requirement_refs.sql`; docs/06 §4.9, §4.11, §5.8; docs/04 §7; docs/07 §5.11, search, Requirements page; docs/08 §15.7; docs/09 M6 row; docs/10 E11; docs/12 glossary.

## 1. Requirement references
- [x] 1.1 Unit tests + `requirements/rules.py` (reference, URL, paste parsing, natural sort, status rules).
- [x] 1.2 Migration 0004; models; repository; service (add many, edit, archive/restore, link/unlink cases, bulk link); plan scope in `planning`.
- [x] 1.3 Coverage SQL (`reporting`) + Python oracle property test; coverage and matrix queries; bugs per reference (API composition).
- [x] 1.4 Schemas, routers, authz matrix, BR manifest (BR-23 → M6).

## 2. Search, filters, saved views
- [x] 2.1 `/search` with per-type queries and indexes; timing test (TCMS-119).
- [x] 2.2 Saved views API (create/list/update/delete, shared rules, defaults); per-list filter declarations.
- [x] 2.3 Missing filter operators on existing lists.

## 3. Frontend
- [x] 3.1 `make api-client`; `features/requirements/` (Requirements page, reference chips, link dialogs, case tab, plan tab, repository bulk + filters).
- [x] 3.2 Traceability page (design) with release picker, summary, filters, expandable rows.
- [x] 3.3 Global search + command palette in the top bar (`/`); saved views menu on lists; "Saved view" tab in Add cases.
- [x] 3.4 Sidebar entries (Requirements, Traceability) and `G Q` / `G T`.

## 4. E2E
- [x] 4.1 `frontend/e2e/m6.spec.ts` (UJ-7, search, palette, saved views).

## 5. Close-out
- [x] 5.1 Seed: SPARK references (some linked, one only on SPARK-PL-1 → Not covered).
- [x] 5.2 All gates; CHECKLIST M6; known limitations (close L19, L25, L34; add M6 deferrals); local-setup.
- [x] 5.3 Commit, push, PR; CI green; report.
