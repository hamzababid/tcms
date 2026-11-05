# M3 — Plans and cycles · Tasks

Ordered per CLAUDE.md §4: write/extend tests for each referenced BR/AC **first**, then implement in the
order migration → models → repository → rules → service → schemas → router → authz-matrix entry →
regenerate API client → frontend (hooks → components → route) → E2E. Each task cites the IDs it satisfies.
Do not start until the spec is approved. Work on branch `milestone/m3-plans-cycles`; never push or merge
without approval.

Tasks are grouped: plans (E07) first since cycles depend on the plan case list, then cycles/runs (E08),
then cross-cutting close-out. Within each group, tests precede implementation.

## 0. Decisions (resolved 2026-11-05 — see design §7)

All open questions are resolved; implementation follows these:

- **Q1** No migration unless a genuine gap surfaces; then migration 0003 + `docs/schema/04_m3_additions.sql`,
  schema-diff + `99_verify.sql` kept green.
- **Q2** `saved_view_id` in add-cases is accepted but returns `422` ("not available until M6"); real support in M6.
- **Q3** Run action endpoint shapes per design §4.2 / §7 item 3 (agent's discretion; docs/06 wins where it fixes a shape).
- **Q4** Build `POST /cycles/{id}/close` with the no-drafts success path and the `409`-lists-drafts contract now.
- **Q5** Build replace-run in M3 against seeded finalized results; ⚠️ **defer the replace-run/retest-round E2E to M4** (see §7.5).
- **Q6** M3 builds explicit `POST /cycles/{id}/start`; BR-30 auto-start lands with the runner in M4.
- **Q7** Audit action names follow `entity.verb_past` and must match docs/02 §13.1; add any missing to §13.1 as a doc change.

## 1. Plans — tests first (E07)

- [x] 1.1 Write API/unit tests for plan CRUD and fields — `tests/api/test_planning.py`,
  `tests/unit/test_planning_rules.py`: create/patch validation (name 3–150, type enum, status enum,
  end ≥ start, risks ≤ 50, exit_rules structured), key `PL` allocation (BR-16), audit on create/update.
  **Satisfies:** FR-PLN-001, FR-PLN-005, BR-16, TCMS-050.
- [x] 1.2 Write tests for case selection + exclusions report (`test_br_13_*`): add by case_ids/folder_ids/
  include_subfolders/tags; snapshot of explicit ids; added/skipped counts; archived excluded (BR-13);
  remove cases; remove does not affect cycles. **Satisfies:** FR-PLN-002, BR-13, TCMS-051.
- [x] 1.3 Write tests for requirement links, clone, and plan-cases-with-results view: link/unlink
  requirements (validated against existing rows), clone copies all-but-cycles as draft "Copy of …",
  `GET /test-plans/{id}/cases` returns latest result per linked cycle. **Satisfies:** FR-PLN-003,
  FR-PLN-004, FR-PLN-006, R-072/073/074.

## 2. Plans — implementation (E07)

- [x] 2.1 Migration: **none expected** (tables exist). If Q1 surfaces a gap, add migration 0003 +
  `docs/schema/04_m3_additions.sql` and keep schema-diff + `99_verify.sql` green. **Satisfies:** docs/05.
- [x] 2.2 Models: reuse `planning/models.py` as-is (confirm fields match docs/05 §3.4). **Satisfies:** docs/05 §3.4.
- [x] 2.3 `planning/repository.py`: scoped inserts/queries for `test_plans`, `test_plan_cases`,
  `test_plan_requirements`, `test_plan_environments` (all via `ScopedQuery.project`). **Satisfies:** docs/04 §3.4.
- [x] 2.4 `planning/rules.py`: field validation, `end ≥ start`, risks cap, exit_rules shape, BR-13
  exclusion reasons, clone rules. **Satisfies:** FR-PLN-001/005, BR-13.
- [x] 2.5 `planning/service.py`: `create_plan`, `update_plan`, `add_cases`, `remove_cases`,
  `link_requirements`/`unlink_requirements`, `clone_plan`, `archive_plan` — each permission-checked,
  validated, audited, one transaction. `add_cases` accepts `saved_view_id` but rejects it with `422`
  ("not available until M6") per Q2. `planning/queries.py`: public reads (plan, plan cases with
  per-cycle results) for other modules and the router. **Satisfies:** FR-PLN-001/002/003/004/006, BR-13/16.
- [x] 2.6 `planning/schemas.py` + `planning/errors.py`: Pydantic request/response models, DomainError
  subclasses mapping to docs/06 §3 codes. **Satisfies:** docs/06 §4.5.
- [x] 2.7 `api/v1/plans.py`: routes per design §4.1 with `project_context_from`, `row_version`,
  `Idempotency-Key` on create. **Satisfies:** docs/06 §4.5.
- [x] 2.8 Add every plan route to `tests/api/authz_matrix.py` with a probe; confirm the OpenAPI-coverage
  guard passes. **Satisfies:** TCMS-012.

## 3. Cycles and runs — tests first (E08)

- [x] 3.1 Write version-pinning + create-cycle tests (`test_br_03_*`, `test_br_12_*`): eligible_version
  (archived→None, deprecated→None for new_cycle, approved-vs-latest by project flag); one run per case;
  duplicates skipped (BR-12); AC-PLN-01 (200 cases, 3 archived + 2 deprecated → 195 runs, 5 skipped with
  reasons). **Satisfies:** BR-03, BR-12, BR-13, AC-PLN-01, TCMS-052.
- [x] 3.2 Write background-creation test (`cycle.create_runs`): 5,000 cases → `202 runs_pending`, job
  completes, runs exist, cycle `runs_pending=false`. **Satisfies:** docs/02 §7.1, TCMS-054.
- [x] 3.3 Write add/remove-runs tests: add skips duplicates and closed cycle; remove only not_run without
  attempts else `409 run_has_results`. **Satisfies:** FR-EXE-003, BR-12, TCMS-057.
- [x] 3.4 Write assign/claim tests: bulk assign (assignee must have `run.execute`) + notification;
  claim pool run → assigned to self. **Satisfies:** FR-EXE-004, TCMS-055, TCMS-056.
- [x] 3.5 Write lifecycle tests: start (planned→active); close no-drafts success + `409`-lists-drafts
  contract (seeded draft fixture per Q4); reopen `403`/`422`/success (`test_br_11_*`); clone with
  `only_statuses`; archive closed-only. **Satisfies:** FR-EXE-012, BR-11, TCMS-058, TCMS-059, TCMS-060.
- [x] 3.6 Write sync-from-plan tests (`test_br_31_*`): adds new plan cases, never removes runs with
  results; AC-PLN-02 (add 10 to plan → unchanged until sync → +10 runs). **Satisfies:** BR-31, AC-PLN-02,
  TCMS-053.
- [x] 3.7 Write version-action tests (`test_br_04_*`, `test_br_05_*`): update-to-latest only on no-attempt
  runs, `409 already_latest` when current; replace-run supersedes old (keeps results, new not_run at
  latest), hidden unless `include_superseded` — unit-tested against seeded finalized results per Q5.
  **Satisfies:** FR-EXE-011, BR-04, BR-05.
- [x] 3.8 Write reorder + progress tests: reorder persists `position`, sort-by-folder/priority
  deterministic; `GET /cycles/{id}` progress by status/assignee/folder equals ExecutionSummary counts.
  **Satisfies:** FR-EXE-013, docs/02 §7.1, R-083, R-087.
- [x] 3.9 Write TCMS-025b test: archived environment not selectable for a new cycle → `422`.
  **Satisfies:** AC-WS-03, TCMS-025b.

## 4. Cycles and runs — implementation (E08)

- [x] 4.1 Migration: none expected (see 2.1 / Q1). **Satisfies:** docs/05 §3.5.
- [x] 4.2 Models: reuse `execution/models.py` (`TestCycle`, `TestRun`) as-is; confirm against docs/05 §3.5.
- [x] 4.3 `execution/repository.py`: scoped inserts/queries for `test_cycles`, `test_runs`; the BR-12
  active-run guard; superseded bookkeeping (deferrable FK, old marked before new per docs/04 §5.7);
  progress aggregation queries using `ix_test_runs__cycle_status`. **Satisfies:** docs/04 §5, docs/05 §3.5.
- [x] 4.4 `execution/rules.py`: `eligible_version` (BR-03/13), create/add selection + skip reasons,
  remove-run guard (BR-12/run_has_results), lifecycle transitions (BR-11), update-version (BR-04),
  replace-run (BR-05), reorder, environment-active check (TCMS-025b). **Satisfies:** BR-03/04/05/11/12/13,
  AC-WS-03.
- [x] 4.5 `execution/service.py`: `create_cycle` (inline ≤500 / enqueue `cycle.create_runs` >500),
  `add_cases`, `remove_runs`, `assign_runs`, `claim_run`, `start`/`close`/`reopen`/`clone`/`archive`,
  `sync_from_plan`, `update_version`(+bulk), `replace_run`, `reorder_runs` — permission-checked, validated,
  audited, one transaction; notifications on assignment. `execution/jobs.py`: `cycle.create_runs` handler.
  `execution/queries.py`: public reads (cycle, summary, runs, progress). **Satisfies:** FR-EXE-001/002/003/
  004/011/012/013, BR-03/04/05/11/12/13/31, AC-PLN-01/02, AC-WS-03.
- [x] 4.6 `execution/schemas.py` + `execution/errors.py`: request/response models (incl. `summary`,
  `skipped[]`, `runs_pending`), DomainError subclasses → docs/06 §3 codes. **Satisfies:** docs/06 §4.6.
- [x] 4.7 `api/v1/cycles.py` and `api/v1/runs.py`: routes per design §4.2 (create → 201/202, lifecycle,
  sync, runs list/add/remove, assign/claim/update-version/replace/reorder) with `project_context_from`,
  `row_version`, `Idempotency-Key`. **Satisfies:** docs/06 §4.6.
- [x] 4.8 Add every cycle/run route to `tests/api/authz_matrix.py` with probes; confirm the OpenAPI
  coverage guard passes (cycle.manage / cycle.reopen / run.execute / project.view). **Satisfies:** TCMS-012.

## 5. API client + frontend

- [x] 5.1 `make api-client`; commit `backend/openapi.json` + `frontend/src/api/schema.d.ts`; confirm
  `make api-client-check` passes (no drift). **Satisfies:** US-005 gate.
- [x] 5.2 Frontend `features/plans/`: hooks (TanStack Query) → components → routes `/p/:projectKey/plans`,
  `/plans/:planKey` (fields form, cases tab with per-cycle results, requirements tab stub, clone/archive).
  Reuse DataTable/StatusBadge/dialogs/tokens; sidebar entry gated on merge. **Satisfies:** US-070…074,
  docs/07, docs/04 §11.
- [x] 5.3 Frontend `features/cycles/`: hooks → components → routes `/p/:projectKey/cycles`,
  `/cycles/:cycleKey` (summary/progress by status/assignee/folder, runs DataTable with filters/sort,
  add/remove/assign/claim/update-version/replace/reorder, lifecycle actions). No runner route (M4).
  **Satisfies:** US-080…087, docs/07, docs/04 §11.

## 6. End-to-end

- [x] 6.1 E2E (`frontend/e2e/m3.spec.ts`): create a cycle from a plan, see skipped cases, assign in bulk,
  claim a pool run, reorder, close/reopen/clone; axe on every visited screen; reuse seeded sessions.
  **Satisfies:** AC-PLN-01/02, TCMS-052/053/055/056/058/059/060, docs/08.

## 7. Close-out (required)

- [x] 7.1 Run `make lint test` and `make e2e`; fix everything (ruff, mypy, import-linter 11 contracts,
  eslint, tsc, prettier, pytest, vitest, Playwright). Do not weaken or skip tests.
- [x] 7.2 Run `99_verify.sql` as `tcms_app` on a fresh DB (`make schema-check` /
  `pytest tests/integration/test_schema.py`); expect **35 PASS**. If migration 0003 was added, confirm the
  schema diff is empty and the role-privilege test passes.
- [x] 7.3 Verify the workflow in the running stack: `make up && make migrate && make seed`, then manually
  create a plan, add cases, create a cycle from it (see skipped cases), assign/claim, update a not-run
  run's version, close and reopen the cycle, sync from plan.
- [x] 7.4 Add `M3` to `tests/br_manifest.COMPLETED`; confirm BR-03/04/05/11/12/31 (and the M3 slice of
  BR-30) are covered by `test_rule_coverage.py`.
- [x] 7.5 Update `docs/ops/CHECKLIST.md`: mark M3 stories ✅ with their test paths and acceptance evidence;
  move resolved known-limitations; note any new deferrals. ⚠️ **Record the Q5 deferral explicitly in
  `docs/ops/known-limitations.md`**: replace-run/BR-05 is built and unit-tested in M3, but its
  retest-round **E2E is deferred to M4** (add when the runner lands). Also note the runner-dependent tails
  (close-with-live-drafts, BR-30 auto-start) that complete in M4. Update `docs/ops/HANDOFF-kiro.md` only if
  behaviour or contracts changed.
- [x] 7.6 Summarize per CLAUDE.md §4.5: what changed, which ACs are covered by which tests, any doc
  conflicts found (e.g. audit action names per Q7), any follow-ups. Stop for review before merge.

## 8. Rework after review (review.md)

- [x] 8.1 Backend contract per docs/02, 04, 06 (review.md §1–2: S1–S7, B1–B17), tests rewritten
  (`tests/api/test_execution.py`, `test_planning.py`, `unit/test_metrics.py`, authz matrix). Commit `f8993aa`.
- [x] 8.2 `status.ts` plan/cycle kinds; `ProgressBar` optional in-progress segment; `useResolvedKey`,
  `useRecordHistory`; History tabs (`features/projects/RecordHistory.tsx`).
- [x] 8.3 Plans: `PlanForm` (all docs/07 §5.7 fields, exit-rule editor, risks table, server errors on
  fields, conflict dialog), list with filters, detail tabs Overview / Cases / Cycles / History, Add cases
  dialog (Folder / Tag / Search) with added/skipped, remove cases, clone, archive, status actions.
- [x] 8.4 Shared `testdesign/CaseSelector.tsx` (`CaseSelector`, `AddResult`, `AddCasesDialog`).
- [x] 8.5 Cycles: list with progress and filters; stepped create dialog (basics, plan + filters or
  repository, default assignee; result with skipped reasons); detail per docs/design/CycleDetail
  (meta line, Add cases, Assign ▾, ⋯ menu, closed banner, runs-pending polling, progress card,
  All / By assignee / By folder, runs table filters, bulk assign/unassign/update/remove, superseded
  toggle); run side panel `?run=` (newer-version banner, update, replace, claim, attempts).
- [x] 8.6 Routes resolve keys via `/resolve`; index routes (review F1); `G C`; audit entity types.
- [x] 8.7 Repository bulk "Add to plan" / "Add to cycle"; project archive offers to close open cycles.
- [x] 8.8 E2E `frontend/e2e/m3.spec.ts` (8 journeys, axe on every screen); Ayesha session for reopen.
- [x] 8.9 Close-out docs: CHECKLIST M3, known-limitations L21–L27, local-setup seed.
