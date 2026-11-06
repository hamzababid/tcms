# M6 — Requirement references, traceability and search · Requirements

| Field | Value |
| --- | --- |
| Milestone | M6 (docs/09 §2), re-scoped on 2026-11-06 by the product owner: requirements stay in each team's tool (Jira, Azure DevOps, …); Assay stores **references** to them, links them to cases and computes coverage. Same approach as ADR-023 for bugs (new ADR-024) |
| Epics | E11 Requirements → **Requirement references and traceability**; E12 Search, filters, saved views (unchanged) |
| Replaces | Requirement authoring in Assay: description, acceptance criteria, type, priority, owner, status, parent tree (FR-REQ-001 as first written), CSV import of requirement text (FR-REQ-003) |
| Carried from earlier | L19 (requirement filters in the repository), L25 (plan Requirements tab; saved-view tab in "Add cases"), L34 (requirement-level bugs) |
| Out of scope | Reading requirement title/status from the tool (connector, P2); PDF export and historical coverage (FR-REQ-007, P2); readiness evaluation and dashboards (M7); list export (M8) |

## Concept

A **requirement reference** is the team's identifier for a requirement or story (`SPK-120`, `AB#4410`, `REQ-7`), with an optional URL (from a project template) and an optional short title. It exists once per project. It is linked to test cases (many-to-many) and to test plans (the requirements a plan must cover). Assay computes per release whether each reference is covered and passing. Assay does not store the requirement's text, type, owner, status or hierarchy.

## Business rules

- **BR-23 (rewritten)** — Requirement coverage and status are computed per release from the requirement's linked cases (§ coverage below).
- **New** — A reference is **in scope for release R** when it is linked to a test plan whose `release_id = R`, or any of its linked cases has a run in a cycle whose `release_id = R`. Without a release, every non-archived reference of the project is in scope.

## Coverage (docs/02 §10.5, adapted)

For release R and reference Q: `linked_cases(Q)` = linked cases whose status ≠ archived. Covered ⇔ ≥ 1. `latest(C, R)` = latest final attempt (by `finished_at`) among non-superseded runs of C in cycles of R, ignoring `not_applicable`. Status: `not_covered` → `failed` (any failed) → `blocked` (any blocked) → `not_run` (any null or skipped) → `passed`. Metrics: total (in scope, not archived), covered, not covered, passed, failed, blocked, not run, coverage % = covered ÷ total, verified % = passed ÷ total (numerator and denominator shown).

## AC

- **AC-REQ-01…04** — unchanged from docs/02 §10.5 (not_run with an unrun case; failed wins; only an archived case → not_covered; a later passing retest in the same release counts).
- **AC-REQ-05** — Given `SPK-120` added to plan P of release R with no linked case, then the matrix for R shows `SPK-120` as Not covered (the gap list).
- **AC-REQ-06** — Given the template `https://acme.atlassian.net/browse/{ref}`, when `SPK-120` is added without a URL, then its URL is built from the template; references compare case-insensitively and are unique per project (`409 already_exists` returns the existing one).
- **AC-SRCH-01** — Given `SPARK-TC-12`, `TC-12` or `12` typed in search within SPARK, then the case is the first result and Enter opens it.

## Tests (docs/08 §15.7 rewritten)

| ID | Test | Level |
| --- | --- | --- |
| TCMS-110 | Link references and cases from either side and in bulk | API + E2E |
| TCMS-111 | Coverage status per release (AC-REQ-01…05) | Unit + integration (SQL vs Python oracle, property test) |
| TCMS-112 | Traceability matrix filters and gap list | API + E2E |
| TCMS-118 | Global search by key (AC-SRCH-01) | API + E2E |
| TCMS-119 | Global search by text, grouped by type, < 500 ms p95 on the test stack | API (+ timing) |
| TCMS-120 | Saved views: private / shared, default per list | API + E2E |

---

### R-120 · Requirement references (US-120 rewritten)
Project page **Requirements**: add one or many references at once (paste `SPK-120, SPK-121` or one per line), optional URL and title; edit URL/title; archive/restore; filters (text, linked / not linked, plan, release scope). Project setting **Requirement address** with `{ref}` (defaults to the bug tracker address). Permissions: `requirement.manage` adds, edits, archives.

### R-121 · Link references and cases (US-121)
From a case (Requirements tab, "Link requirement" with suggestions), from a reference (its case list, "Link cases" with the repository picker), and in bulk from the repository ("Link selected to requirement…"). `requirement.link`. Audited `requirement.linked` / `requirement.unlinked`. Repository filters `requirement` (reference) and `has_requirements` (L19).

### R-122 · Plan scope (US-072 reworked)
Plan detail gains a **Requirements** tab (L25): add references (paste many), remove, see each one's status for the plan's release. `plan.manage`.

### R-123 · Coverage and status per release (US-122)
`GET /projects/{id}/coverage?release_id=` → metrics; per-reference status in the matrix and on the reference's page. SQL in `requirements/queries.py`, rules in `requirements/rules.py`; a property test compares SQL with a pure-Python oracle on random fixtures.

### R-124 · Traceability matrix (US-123)
Screen per docs/design/Traceability.dc.html without the hierarchy column: release picker, summary line ("Coverage 54 of 60 (90%) · Verified 41 of 60 (68%) · …"), rows = references in scope, columns reference (link + title), cases count, status in release, latest result per case, bugs (M5 chips through the cases' attempts). Filters: release, status, uncovered only, text. Expand a row for case details (cycle, date, executed by). "Link cases" on uncovered rows. Export → M8 (L-item).

### R-130 · Global search (US-130)
Header search (`/`): current project by default, "all projects" toggle. Exact keys (case, plan, cycle; `TC-12`, `12`), titles (prefix + trigram), folder, cycle and plan names, requirement and bug references and titles. Grouped by type, top 5 each, "See all" → the filtered list. Enter on an exact key opens it. Target < 500 ms p95.

### R-131 · Consistent filters (US-131)
Operators of docs/02 §12 on the existing lists (cases, plans, cycles, runs, bugs, requirements) where the field type allows; the DataTable filter row already covers text, select and date range — M6 adds "is not", "is empty" and multi-select ("in") where a list lacks them.

### R-132 · Saved views (US-132)
Name, list (entity type), filters, columns, sort; private or shared (shared needs `cycle.manage`, `plan.manage` or `project.configure`); default per user and list. On the repository, cycle runs, plans, cycles, bugs and requirements lists; "Saved view" tab in the plan's Add cases dialog (L25).

### R-133 · Command palette (US-133)
`>` in the search box lists actions: New test case, New plan, New cycle, Go to My Work / Repository / Plans / Cycles / Bugs / Requirements / Traceability, and the `G` shortcuts.
