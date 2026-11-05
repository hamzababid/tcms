# M3 — Plans and cycles · Design

This design assembles the relevant parts of docs/04 (LLD), docs/05 (Database) and docs/06 (API) for M3 and
describes how the existing code is extended. **Any departure from those docs is listed as a question in
§7, not decided here.**

## 1. Modules and boundaries

Per docs/04 §1 and docs/03 §5.1, M3 touches two domain modules:

- **`planning/`** (plans). Currently only `models.py` exists. Add `errors.py`, `queries.py`,
  `repository.py`, `rules.py`, `schemas.py`, `service.py` following the `testdesign/` templates.
- **`execution/`** (cycles, runs). Currently `models.py` + `queries.py` exist. Add `errors.py`,
  `repository.py`, `rules.py`, `schemas.py`, `service.py`, and `jobs.py` (background run creation).

Module layering (docs/03 §5.1): `execution` sits above `planning` and `testdesign`; `planning` sits above
`testdesign` and `workspace`. Cross-module reads go through the other module's `queries.py` (public),
never its `repository`/`models` (private — import-linter enforces this). So:

- `planning` reads cases via `testdesign.queries` and project flags via `workspace.queries`.
- `execution` reads the plan case list via `planning.queries`, cases/versions via `testdesign.queries`,
  environments/releases/project flags via `workspace.queries`.

Routers live in `api/v1/plans.py`, `api/v1/cycles.py`, `api/v1/runs.py` (names already reserved in
docs/04 §1). Every write goes through a module `service.py` function that checks permission, validates via
`rules.py`, writes, calls `uow.audit(...)` and enqueues side effects as jobs, in one transaction
(CLAUDE.md rule 2).

## 2. Database (docs/05 §3.4–3.5)

**No new migration is required for the M3 core.** All tables, enums, indexes and the BR-12 partial unique
index already exist in the baseline (`docs/schema/01_baseline.sql`, applied by migration 0001) and have
ORM models from M0:

- `test_plans`, `test_plan_cases`, `test_plan_requirements`, `test_plan_environments` (docs/05 §3.4).
- `test_cycles`, `test_runs` (docs/05 §3.5). Enums `plan_type`, `plan_status`, `cycle_status`, `run_status`
  already exist.

Key constraints M3 relies on (already in the baseline):

- `ux_test_runs__cycle_case_active` UNIQUE `(cycle_id, test_case_id) WHERE superseded_by_run_id IS NULL`
  enforces BR-12 at the DB.
- `test_runs.superseded_by_run_id` FK is **DEFERRABLE INITIALLY DEFERRED**; Replace-run sets the old run's
  pointer before the new run exists. (docs/04 §5.7 note: because the partial unique index is on the active
  set, the old run is marked first in the same transaction.)
- `trg_test_runs_version_check` guarantees the pinned version belongs to the run's case; composite FKs
  `(project_id, cycle_id)` / `(project_id, test_case_id)` keep everything in one project.
- `ix_test_runs__cycle_status`, `ix_test_runs__cycle_position`, `ix_test_runs__assignee_status` back the
  runs list, progress and My-Work queries (docs/05 §5).

Key allocation uses the existing `key_sequences` helper (BR-16) that M1/M2 already use for `TC`/`D`; M3
adds `PL` and `CY` prefixes through the same path.

If a schema gap is discovered during implementation (e.g. a column the behaviour needs that the baseline
lacks), it becomes **migration 0003** reproduced as `docs/schema/04_m3_additions.sql`, and the schema-diff
test + `99_verify.sql` must still pass (docs/04 §4.4, G7). See §7 Q1.

## 3. Execution algorithms (docs/04 §5.1–5.2, §5.7)

### 3.1 Eligible version (BR-03, BR-17) — `execution/rules.py` (shared helper)

```
eligible_version(case, settings, purpose) =
   None if case.status == "archived"
   None if purpose == "new_cycle" and case.status == "deprecated"   # BR-13
   case.approved_version_id if settings.approval_required else case.latest_version_id
```

The case status and version ids come from `testdesign.queries`; `settings.approval_required` from
`workspace.queries`. (This mirrors `testdesign` BR-17 handling already in the codebase.)

### 3.2 Create cycle / add cases (docs/04 §5.2)

```
for case in selection:
    v = eligible_version(case, settings, purpose="new_cycle")
    if v is None: skipped.append((case.key, reason)); continue        # archived / deprecated / no_approved_version
    if exists non-superseded run (cycle, case): skipped.append((key, "already_in_cycle")); continue  # BR-12
    insert test_runs(cycle_id, test_case_id, test_case_version_id=v, status='not_run',
                     position=next_pos, assignee_id=default)
audit run.added (one event per run, shared bulk_operation_id)
```

`> 500` cases → enqueue job `cycle.create_runs`; cycle has `runs_pending = true` until the job finishes;
the UI polls `GET /cycles/{id}`. This is the existing job pattern (`platform/jobs`, `@job_handler`,
outbox-enqueued in the same transaction as the cycle insert). Inline path otherwise.

### 3.3 Replace run (docs/04 §5.7)

```
lock run; require cycle.manage; require run has ≥1 final attempt; cycle not closed; not superseded
v = eligible_version(case); require v != run.version (else 409 already_latest)
new = insert test_runs(... version=v, position=run.position, assignee_id=run.assignee_id, status=not_run)
run.superseded_by_run_id = new.id; run.superseded_at = now   # old marked first (partial unique index)
audit run.replaced
```

### 3.4 Update to latest (BR-04)

```
lock run; require (cycle.manage) or (assignee and run.execute); run has no attempts (else 409 run_has_results-equivalent)
v = eligible_version(case); require v != run.version (else 409 already_latest)
run.test_case_version_id = v; audit run.version_updated
```

Bulk "update all not-run runs" iterates the not-run, non-superseded set.

## 4. API (docs/06 §4.5–4.6)

Conventions (docs/06 §2): problem+json errors with the stable codes in §3; `row_version` optimistic
concurrency on mutable aggregates (plans, cycles) via `If-Match`/body (BR-25); `Idempotency-Key` on creates
(the pattern M2 added); offset pagination with `total` (ADR-021); filter/sort allow-lists.

### 4.1 Test plans (docs/06 §4.5)

| Method | Path | Perm | Notes |
| --- | --- | --- | --- |
| GET | `/projects/{project_id}/test-plans` | project.view | filters status, type, release_id, owner_id, q |
| POST | `/projects/{project_id}/test-plans` | plan.manage | all plan fields |
| GET | `/test-plans/{id}` | project.view | `?include=cases,requirements,cycles` |
| PATCH | `/test-plans/{id}` | plan.manage | fields + `row_version` |
| POST | `/test-plans/{id}/cases` | plan.manage | `{case_ids?, folder_ids?, include_subfolders?, tags?, saved_view_id?}` → `{added, skipped[]}` |
| DELETE | `/test-plans/{id}/cases` | plan.manage | `{case_ids}` |
| GET | `/test-plans/{id}/cases` | project.view | paginated, latest results per cycle |
| POST/DELETE | `/test-plans/{id}/requirements` | plan.manage | `{requirement_ids}` |
| POST | `/test-plans/{id}/clone` | plan.manage | `{name?}` |
| POST | `/test-plans/{id}/archive` | plan.manage | |

`saved_view_id` in the add-cases body depends on saved views, which are **M6**. For M3 the add-cases
contract accepts `case_ids`/`folder_ids`/`include_subfolders`/`tags`; `saved_view_id` is accepted in the
schema but returns `422` "not available until M6" rather than a dummy behaviour (no-dummy-UI rule). See §7 Q2.

### 4.2 Cycles and runs (docs/06 §4.6)

| Method | Path | Perm | Notes |
| --- | --- | --- | --- |
| GET | `/projects/{project_id}/cycles` | project.view | filters status, release_id, plan_id, environment_id, owner_id, q; each item has `summary` |
| POST | `/projects/{project_id}/cycles` | cycle.manage | `{name, environment_id, release_id?, plan_id?, build?, start_date?, due_date?, description?, selection: {from_plan?, case_ids?, folder_ids?, tags?, priorities?}, default_assignee_id?}` → `201 {cycle, added, skipped[]}` or `202 runs_pending=true` |
| GET | `/cycles/{id}` | project.view | cycle + summary + progress by assignee and folder |
| PATCH | `/cycles/{id}` | cycle.manage | name, description, build, dates, environment (only if no attempts) |
| POST | `/cycles/{id}/start` | cycle.manage | planned → active |
| POST | `/cycles/{id}/close` | cycle.manage | `{discard_drafts?}`; `409` lists drafts if any and not discarding |
| POST | `/cycles/{id}/reopen` | cycle.reopen | `{reason}` |
| POST | `/cycles/{id}/clone` | cycle.manage | `{name, only_statuses?: [failed, blocked, not_run]}` |
| POST | `/cycles/{id}/archive` | cycle.manage | closed only |
| POST | `/cycles/{id}/sync-from-plan` | cycle.manage | BR-31 → `{added}` |
| GET | `/cycles/{id}/runs` | project.view | filters status, assignee_id (`me`,`none`), folder_id, priority, needs_retest, tag, q, include_superseded; sort position, key, status, priority, updated_at |
| POST | `/cycles/{id}/runs` | cycle.manage | add cases `{case_ids?, folder_ids?, tags?}` → `{added, skipped[]}` |
| DELETE | `/cycles/{id}/runs` | cycle.manage | `{run_ids}` (only not_run without attempts) |

Additional run endpoints implied by docs/02 §7.2 / docs/06 §4.6 (version actions and assignment):

| Method | Path | Perm | Notes |
| --- | --- | --- | --- |
| POST | `/cycles/{id}/runs/assign` | cycle.manage | bulk `{run_ids, assignee_id?}` (null = unassign) |
| POST | `/runs/{id}/claim` | run.execute | assign unassigned run to self |
| POST | `/runs/{id}/update-version` | cycle.manage or assignee+run.execute | BR-04; bulk variant on the cycle for all not-run |
| POST | `/runs/{id}/replace` | cycle.manage | BR-05 |
| POST | `/cycles/{id}/runs/reorder` | cycle.manage | `{ordered_run_ids}` or `sort_by: folder\|priority` |

The exact path/shape for assign/claim/update-version/replace/reorder will be confirmed against docs/06
§4.6 during implementation; where docs/06 already fixes a shape it wins (endpoint shape → API Spec wins).
See §7 Q3.

**Error codes used** (already in docs/06 §3 catalog): `409 cycle_closed`, `409 run_has_results`,
`409 run_superseded`, `409 already_latest`, `422 no_eligible_version`, `422 validation_error`,
`422 reason_required` (reopen), `409 name_taken`, `409 project_archived`, `409 stale_row_version`,
`403 permission_denied`, `404 not_found`. TCMS-025b uses `422` for an archived environment on create.

## 5. How the existing code is extended

- **Permissions:** `plan.manage`, `cycle.manage`, `cycle.reopen`, `run.execute` are already defined in the
  core permission registry and seeded into `role_permissions` (M1, verified by
  `test_seeded_role_permissions_match_code_registry`). No permission or role changes.
- **Models:** reuse the existing `planning/models.py` and `execution/models.py` as-is. If a column is
  missing, see §7 Q1 (migration 0003).
- **Key allocation:** reuse the `key_sequences` BR-16 helper; register `PL` and `CY` entity prefixes.
- **Jobs:** reuse `platform/jobs`; add a `cycle.create_runs` handler in `execution/jobs.py`, enqueued in
  the create-cycle transaction (outbox).
- **Audit:** new action names follow `entity.verb_past`: `test_plan.created`, `test_plan.updated`,
  `test_plan.cases_added`, `test_plan.cases_removed`, `test_plan.archived`, `test_cycle.created`,
  `test_cycle.started`, `test_cycle.closed`, `test_cycle.reopened`, `test_cycle.archived`,
  `test_cycle.synced_from_plan`, `run.added`, `run.removed`, `run.assigned`, `run.claimed`,
  `run.version_updated`, `run.replaced`, `run.reordered`. All match the `^[a-z_]+\.[a-z_]+$` audit CHECK.
  Exact names are confirmed against docs/02 §13.1 during implementation (behaviour → Functional Spec wins).
- **Authz matrix:** every new route gets an entry in `tests/api/authz_matrix.py` with a probe; the existing
  "every OpenAPI operation is in the matrix" guard test keeps coverage complete (TCMS-012 pattern).
- **API client:** `make api-client` regenerates `frontend/src/api/schema.d.ts` from the new OpenAPI; the
  drift gate (`make api-client-check`) must pass.

### Frontend (docs/04 §11, docs/07, docs/design)

Add features `plans/` and `cycles/` under `frontend/src/features/`, and routes
`/p/:projectKey/plans`, `/plans/:planKey`, `/p/:projectKey/cycles`, `/cycles/:cycleKey` (docs/04 §11 route
table). Reuse the shared `DataTable`, `StatusBadge`, `ProgressBar`, `Metric`, `UserPicker`, `FolderTree`,
dialogs and tokens from the design-system pass — never copy the design HTML (docs/design is a visual
reference only, per steering 40-frontend). Server state via TanStack Query only. Sidebar entries for Plans
and Cycles appear only once their screens are merged (no-dummy-UI rule). The runner route
(`/cycles/:cycleKey/run/:runId`) is **M4** and is not added here.

Screens for M3: plan list + plan detail (fields, cases tab with per-cycle results, requirements tab stub,
clone/archive actions); cycle list + cycle detail (summary/progress by status/assignee/folder, runs
`DataTable` with filters/sort, add/remove/assign/claim/update-version/replace/reorder actions, lifecycle
actions). Design reference screens: `docs/design/CycleDetail.dc.html`, `Readiness.dc.html` (readiness is
M7; use for cycle layout only).

## 6. Testing approach (docs/08)

- BR/AC tests first (docs/08 §4, CLAUDE.md §4): `test_br_03_*`, `test_br_04_*`, `test_br_05_*`,
  `test_br_11_*`, `test_br_12_*`, `test_br_30_*` (trigger stubbed for M4), `test_br_31_*`, and TCMS-025b,
  050–060 with docstrings citing the AC/TCMS IDs.
- Authz matrix for every new route (TCMS-012 harness); cross-tenant/non-member 404 probes.
- Background path: an integration test for `cycle.create_runs` (TCMS-054, 5,000 cases → `runs_pending`
  then complete).
- Add `M3` to `tests/br_manifest.COMPLETED` only when M3 acceptance passes; map BR-03/04/05/11/12/31 (and
  the M3 slice of BR-30) accordingly — they are already listed with milestone `M3` in `br_manifest.py`.
- E2E: a cycle-detail journey (create cycle from plan, assign, claim, lifecycle) with axe, per docs/08.

## 7. Questions (departures from the docs — decide before implementing)

1. **Q1 — Any schema change needed?** The baseline appears complete for M3; the plan is **no migration**.
   If implementation reveals a missing column (e.g. a per-run label, or a `runs_pending` progress counter
   beyond the existing boolean), is adding migration 0003 (+ `docs/schema/04_m3_additions.sql`, schema-diff
   and `99_verify.sql` kept green) acceptable, or should any such need be raised to you first?
2. **Q2 — `saved_view_id` in add-cases.** Saved views are M6. Proposal: accept the field in the schema but
   return `422` ("not available until M6") rather than silently ignoring it. Acceptable, or omit the field
   from the M3 schema entirely until M6?
3. **Q3 — Run action endpoint shapes.** docs/06 §4.6 lists cycle/run endpoints; assign/claim/
   update-version/replace/reorder shapes above are my reading. Where docs/06 fixes a shape it wins; where
   it is silent I will follow the table in §4.2. Any shape you want fixed up front?
4. **Q4 — Close-cycle drafts contract in M3.** Draft attempts only exist with the runner (M4). Proposal:
   build `POST /cycles/{id}/close` now returning the "no drafts" success path and the `409`-lists-drafts
   contract (exercised with a seeded draft fixture) so M4 needs no contract change. Acceptable?
5. **Q5 — Replace-run / BR-05 in M3 vs M4.** Replace-run needs a finalized attempt, which is M4. Proposal:
   build the endpoint + rules + superseded bookkeeping in M3 and unit-test against seeded finalized
   `test_results` rows; defer the full retest-round E2E to M4. Acceptable, or move US-086 entirely to M4?
6. **Q6 — BR-30 auto-start.** "Executing a run in a Planned cycle moves it to Active" fires from the
   runner (M4). M3 builds the explicit `POST /cycles/{id}/start` and leaves the auto-trigger to M4. Confirm
   this split (it matches docs/09 M4 scope).
7. **Q7 — Audit action names.** The names in §5 follow `entity.verb_past`. Please confirm they should match
   whatever docs/02 §13.1 lists; if §13.1 omits some of these M3 actions, I will add them to §13.1 as a
   doc change (behaviour → Functional Spec wins) and note it, rather than inventing silently.
