# M5 — Bug links · Tasks

Order per CLAUDE.md §4: docs, tests first, rules → migration → service → schemas → router → authz →
client → frontend → E2E → close-out. Decisions D1–D13 in design.md §1; D10 (Q1) taken as proposed: the product owner said "go ahead".

## 0. Docs (re-scope)

- [x] 0.1 docs/11: ADR "Bugs live in the team's tracker; Assay links to them" (D1).
- [x] 0.2 docs/01: FR-DEF rewritten as bug links; BR-19/22 retired, BR-20/21 rewritten; UJ-6; MVP gate wording; RK-04 / AS-02.
- [x] 0.3 docs/02: §8 rewritten (bug links); §2.7 defect notifications removed; §3.1 permission descriptions (D5); §4.2 settings (D8, rename); §7.3 `bug_link_required`; §7.5 My Work; §10 RTM; §11.4 rule (D10); §13.1 audit names `bug.*`.
- [x] 0.4 docs/05 §3.6 + `docs/schema/04_m5_bug_links.sql`; docs/06 §4.7–4.8, §5.6, error codes; docs/04 §6; docs/07 §5.8–5.10, §5.13, §5.14; docs/08 §15.6; docs/09 M5 row; docs/10 E10; docs/ops/00-review.md K17j "superseded".

## 1. Rules and storage (tests first)

- [x] 1.1 Unit tests `test_bug_rules.py`; `bugs/rules.py`.
- [x] 1.2 Alembic migration: `bug_links`, settings key rename, D10 rule migration; `make schema-check` against the new baseline file; import-linter layer `bugs`.

## 2. Backend

- [x] 2.1 API + integration tests (`test_bug_links.py`, retest, finalize setting).
- [x] 2.2 `bugs` module: models, repository, service, handlers; execution events + `flag_runs_for_retest` + `attempt_context`.
- [x] 2.3 Queries, schemas, `api/v1/bugs.py`; `bug_links` on run read and runs list; case bug links; bug report.
- [x] 2.4 Settings (workspace) and readiness rule (planning).
- [x] 2.5 Authz matrix; BR manifest; coverage gate.

## 3. Frontend

- [x] 3.1 `make api-client`; `features/bugs/api.ts`.
- [x] 3.2 Popover, chip, copy bug details; runner integration (`D`, footer, required link on Finish).
- [x] 3.3 Run panel/history chips; cycle Bugs column + needs-retest filter; case Bugs tab.
- [x] 3.4 Project Bugs page + Ready for retest; sidebar + `G D`.
- [x] 3.5 Project settings fields; plan form rule (D10).

## 4. E2E

- [x] 4.1 `frontend/e2e/m5.spec.ts`; update m3.spec.ts if the readiness rule changes.

## 5. Close-out

- [x] 5.1 Seed (tracker settings, `SPK-431` on SPARK-CY-1, a case link).
- [x] 5.2 All gates: lint, backend + coverage gate, timing, schema-check, api-client-check, vitest, E2E.
- [x] 5.3 CHECKLIST M5; known-limitations (close L26, L28; add "no tracker status", "connector P2"); local-setup.
- [x] 5.4 Commit, push, PR; CI green; report.
