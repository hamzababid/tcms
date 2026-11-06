# M6 — Requirement references, traceability and search · Design

## 1. Decisions

**(Q)** = needs the product owner's answer before building; the rest are my calls and can be overridden.

| # | Topic | Decision | Why |
| --- | --- | --- | --- |
| D1 | Scope | ADR-024 "Requirements live in the team's tool; Assay links to them" (mirrors ADR-023). PRD FR-REQ-001/003, docs/02 §10, UJ-7 and AS-03 rewritten; FR-REQ-006 (Jira import) becomes "show title/status from the tool by reference" (P2) | Product owner, 2026-11-06 |
| D2 | Storage | New tables (migration 0004, `docs/schema/05_m6_requirement_refs.sql`): `requirement_refs` (id, org, project, reference 1–100, reference_norm unique per project, url http(s), title ≤ 255, archived_at, std), `requirement_ref_cases` (ref_id, test_case_id, created_*), `plan_requirement_refs` (plan_id, ref_id, created_*), composite FKs to the project. The baseline `requirements`, `requirement_case_links`, `test_plan_requirements` stay unused (like the defect tables). One row per reference (unlike bug links) because plans must list references that no case covers yet | Gap list needs a record without cases |
| D3 | Release scope (Q1 = a, product owner 2026-11-06) | A reference is in scope for release R if it is linked to a plan of R **or** a linked case has a run in a cycle of R. Alternative: plans only (stricter: a reference shows in a release only when a plan of that release lists it) | docs/02 §10.3 used `target_release_id`, which references no longer have |
| D4 | Address (Q2 = a, product owner 2026-11-06) | One project setting `requirement_url_template` (http(s) with `{ref}`), defaulting to the bug tracker address when empty, so Jira teams set it once. Alternative: always use the bug address (no new setting) | Some teams keep stories and bugs in different tools |
| D5 | Module and layering | `tcms.requirements` (exists, below planning) keeps the reference registry and case links; plan links live in `planning` (above requirements). Coverage needs execution results, so the coverage SQL lives in `reporting` (reads everything, docs/03) behind `requirements` rules; the API composes. Bugs per reference come from `bugs.queries` in the API layer | CLAUDE.md layering, import-linter |
| D6 | Permissions | Reuse codes: `requirement.manage` (QA Manager, PM/BA) adds/edits/archives references; `requirement.link` (QA Manager, Lead, Engineer, PM/BA) links cases; plan scope needs `plan.manage` | docs/02 §3.1–3.2 |
| D7 | Readiness rules | `min_requirement_coverage` and `min_requirements_verified` keep their meaning over in-scope references (evaluated in M7) | Unchanged contract |
| D8 | Search | PostgreSQL full text + `pg_trgm` (ADR-022), one endpoint `GET /search?q=&project_id=&types=&limit=`, per-type queries with indexes (test case key/title trigram exist; add trigram on requirement/bug references and cycle/plan names where missing). No external engine | docs/06 §4.11 |
| D9 | Saved views | Baseline `saved_views` table (exists). `filters`/`columns`/`sort` as JSON validated against each list's declared filters; unknown fields → 422. Defaults stored per user per entity type in `saved_views.is_default` (check the baseline columns; else `user_preferences`) | docs/02 §12 |
| D10 | Hierarchy | None. A reference has no parent; the matrix is a flat list sorted by reference (natural sort: SPK-2 before SPK-10) | Assay does not hold the tree |
| D11 | Requirement import | "Paste many" (comma, space or newline separated, ≤ 500) replaces CSV import; existing references are reused, not duplicated | FR-REQ-003 shrinks |

## 2. Testing

- Unit: reference/URL/template rules (reuse `bugs.rules` helpers through a shared core helper or duplicate small validators), status rules (AC-REQ-01…04), natural sort, paste parsing, saved-view validation.
- Integration: coverage SQL vs Python oracle (Hypothesis, random cases/runs/attempts across two releases); scope rule (D3).
- API: CRUD, links both sides and bulk, plan scope, coverage endpoint, matrix, search by key/text/type, saved views visibility and defaults, authz matrix, tenancy.
- E2E `m6.spec.ts` (axe): UJ-7 gap list (add references to a plan → matrix shows Not covered → link a case → Not run → execute → Passed), search by key and text, command palette, save and share a view.
