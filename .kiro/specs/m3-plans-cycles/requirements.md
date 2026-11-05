# M3 — Plans and cycles · Requirements

| Field | Value |
| --- | --- |
| Milestone | M3 (docs/09 §2) |
| Epics | E07 Test plans, E08 Cycles and runs (docs/10) |
| Source of truth | docs/02 §6, §7.1, §7.2; docs/01 §7 (BR); docs/06 §4.5–4.6; docs/05 §3.4–3.5; docs/04 §5.1–5.2 |
| Scope note | Only **unfinished** work per docs/ops/HANDOFF-kiro.md §7 is included. The execution runner (recording step results, attempts, finalize, roll-up — FR-EXE-005/006/007/008/009/010, BR-06/07/08/09/10) is **M4** and is out of scope here. M3 builds plans, cycles and run **management** (create/pin/add/remove/assign/claim/version-update/replace/lifecycle/sync/clone/progress) up to the point of execution. |

Acceptance criteria below are copied verbatim from docs/02 (IDs preserved). Business-rule text is copied
verbatim from docs/01 §7. Each requirement cites the FR/BR/AC IDs and the TCMS test IDs from docs/08 §15.4.

Glossary of referenced BRs (docs/01 §7, verbatim):

- **BR-03** — When a run is created it pins one case version: the approved version if the project enforces approval, otherwise the latest version. Cases with no eligible version are excluded with a warning.
- **BR-04** — "Update to latest version" is allowed only while the run has no result attempt (status Not Run).
- **BR-05** — "Replace run" (run has at least one finalized result) creates a new run at the latest eligible version in the same cycle; the old run is marked superseded, keeps its results, and is excluded from metrics.
- **BR-11** — In a Closed cycle no attempts can be started or finalized and assignments cannot change. Reopening requires `cycle.reopen` and a reason.
- **BR-12** — A case appears at most once among the non-superseded runs of a cycle.
- **BR-13** — Archived cases cannot be added to plans or cycles. Deprecated cases cannot be added to new cycles; existing references stay and show a warning.
- **BR-16** — Human-readable keys (`SPARK-TC-123`) are allocated sequentially per project and entity type, never reused, and never change when an item moves.
- **BR-30** — Executing a run in a Planned cycle moves the cycle to Active.
- **BR-31** — Cycles created from a plan snapshot the plan's case list at that moment; later plan changes affect the cycle only via "Sync from plan", which adds new cases and never removes runs with results.

AC referenced (docs/02, verbatim):

- **AC-PLN-01** — Given a plan with 200 cases, 3 archived and 2 deprecated, when a cycle is created from it, then 195 runs are created and the response lists the 5 skipped cases with reasons.
- **AC-PLN-02** — Given a cycle created from a plan, when 10 cases are added to the plan, then the cycle is unchanged until "Sync from plan" is run, which adds 10 runs.
- **AC-WS-03** — Given an environment used by an active cycle, when it is archived, then the cycle keeps working and the environment is not selectable for new cycles. *(The M1 part — archived environment hidden from pickers — is done. M3 adds the "not selectable for new cycle" enforcement: TCMS-025b.)*

---

## E07 — Test plans

### R-070 · Create a test plan (US-070)
**Refs:** FR-PLN-001, FR-PLN-005 · **Tests:** TCMS-050

As a QA Manager, I create a plan with all fields so I can organise a test effort.

Fields and rules (docs/02 §6.1): `name` 3–150 required; `type` ∈ {`functional`, `integration`,
`regression`, `release_validation`, `uat`, `smoke`, `performance`, `security`}; `release_id` optional;
`status` ∈ {`draft`, `active`, `completed`, `archived`} (default `draft`); `objectives`, `scope_in`,
`scope_out`, `entry_criteria`, `acceptance_criteria` Markdown; `environment_ids` list; `exit_criteria` =
list of readiness rules (docs/02 §11.4) stored in `exit_rules` + Markdown notes in `exit_criteria_notes`;
`risks` list of `{description, impact: low/medium/high, mitigation}` max 50; `start_date`/`end_date` with
`end ≥ start`; `owner_id` default creator; `member_ids` QA resources. Key `SPARK-PL-n` auto-allocated
(BR-16). Permission `plan.manage`. Audit `test_plan.created`.

**Acceptance (docs/08 TCMS-050):** plan saved; exit rules are evaluable (stored as structured readiness
rules, not free text — FR-PLN-005).

### R-071 · Select cases into a plan (US-071)
**Refs:** FR-PLN-002, BR-13 · **Tests:** TCMS-051

As a QA Manager, I add cases to a plan by individual pick, whole folder (with/without subfolders), tag, or
saved filter. Selection is stored as **explicit case IDs** (snapshot), not as a rule (docs/02 §6.2). The
add response reports how many cases each rule adds and how many are excluded (archived/deprecated/
unapproved). Removing cases is free and does not affect existing cycles. BR-13: archived cases cannot be
added. Permission `plan.manage`.

**Acceptance (docs/08 TCMS-051):** added/skipped counts correct; the exclusions report lists skipped cases
with reasons.

### R-072 · Link requirements to a plan (US-072)
**Refs:** FR-PLN-003 · **Tests:** — (fully enabled after M6)

As a QA Manager, I link requirements to a plan. In M3 this is the `test_plan_requirements` write/read path
only (`POST/DELETE /test-plans/{id}/requirements`); the requirements module itself is M6, so link targets
are validated against existing `requirements` rows but the RTM/coverage view is out of scope here.
Permission `plan.manage`.

**Acceptance:** requirement links persist and round-trip; linking a non-existent/other-project requirement
is rejected. (No AC in docs/02 beyond FR-PLN-003; coverage behaviour is M6.)

### R-073 · Clone a plan (US-073)
**Refs:** FR-PLN-006 · **Tests:** —

As a QA Manager, I clone a plan. Clone copies everything **except cycles**; name "Copy of …"; status
`draft` (docs/02 §6.3). Permission `plan.manage`. Audit `test_plan.created` (clone source noted).

**Acceptance (docs/02 §6.3):** the clone has the same fields, case list and requirement links as the
source, no cycles, name "Copy of <name>", status `draft`.

### R-074 · View plan cases with latest results per cycle (US-074)
**Refs:** FR-PLN-004 (plan reusable across cycles), docs/02 §6.2/§6.3 · **Tests:** —

As a QA user, I view a plan's cases with, per case, the latest result in each linked cycle (docs/02 §6.2),
and I see the plan's cycles (a plan can have any number of cycles — FR-PLN-004). Permission `project.view`.
`GET /test-plans/{id}/cases` is paginated with latest results per cycle; `GET /test-plans/{id}?include=cycles`.

**Acceptance:** plan cases list shows one column per linked cycle with the latest run status for that case;
a plan with no cycles shows the cases with no result columns.

---

## E08 — Cycles and runs

### R-080 · Create a cycle from a plan or the repository (US-080)
**Refs:** FR-EXE-001, FR-EXE-002, BR-03, BR-12, BR-13, BR-16 · **Tests:** AC-PLN-01 / TCMS-052, TCMS-054

As a QA Lead, I create a cycle from a plan or directly from the repository, with release, environment,
dates and description. The cycle contains one run per selected case (BR-12), each pinned to a case version
(BR-03: approved version if the project enforces approval, else latest; cases with no eligible version
excluded with a warning). Cases can be selected `from_plan` or by `case_ids`/`folder_ids`/`tags`/
`priorities`. `environment_id` must be an **active** environment (AC-WS-03 / TCMS-025b: an archived
environment is **not selectable for new cycles** → `422`). More than 500 runs are created in the
background (`runs_pending=true`, `202`, progress shown). Key `SPARK-CY-n` (BR-16). Each created run is
audited `run.added` with a shared `bulk_operation_id`. Permission `cycle.manage`.

**Acceptance (docs/02 AC-PLN-01, verbatim):** Given a plan with 200 cases, 3 archived and 2 deprecated,
when a cycle is created from it, then 195 runs are created and the response lists the 5 skipped cases with
reasons.
**Also (docs/08 TCMS-054):** a cycle with 5,000 cases is created in the background — `runs_pending` then
complete.
**Also (docs/08 TCMS-025b):** an archived environment is not selectable for a new cycle → `422`.

### R-081 · Add and remove cases in a cycle (US-081)
**Refs:** FR-EXE-003, BR-12 · **Tests:** TCMS-057

As a QA Lead, I add and remove cases in a cycle. Add: not allowed in a closed cycle (`409 cycle_closed`);
duplicates skipped (BR-12); eligible version pinned (BR-03); deprecated cases cannot be added to the cycle
(BR-13). Remove: only runs with status `not_run` and no attempts, otherwise `409 run_has_results`.
Permission `cycle.manage`.

**Acceptance (docs/08 TCMS-057):** removing a run that has results is refused with `409 run_has_results`;
adding an already-present case is skipped (BR-12); adding to a closed cycle is refused.

### R-082 · Assign, unassign and claim runs (US-082)
**Refs:** FR-EXE-004 · **Tests:** TCMS-055, TCMS-056

As a QA Lead, I assign runs to testers individually or in bulk, or leave them unassigned in a team pool
that testers can claim. Assignee must be a project member holding `run.execute`. Assignment is a
`cycle.manage` action; claiming an unassigned run (→ assigned to self) requires `run.execute`. Assignment
notifies the assignee (docs/02 §2.7 "Runs assigned to me": in-app + daily email digest, opt-out).

**Acceptance (docs/08 TCMS-055):** bulk assign by folder sets assignees and sends notifications.
**Also (docs/08 TCMS-056):** a tester claims a pool (unassigned) run and it becomes assigned to the claimer.

### R-083 · Cycle progress by status, assignee and folder (US-083)
**Refs:** FR-EXE-013 · **Tests:** — (numbers verified equal to ExecutionSummary)

As a QA Lead, I see cycle progress broken down by status, by assignee and by folder. `GET /cycles/{id}`
returns the cycle plus `summary` (counts by status) and progress by assignee and folder. Non-superseded
runs only. Permission `project.view`.

**Acceptance (docs/02 §7.1, docs/10 US-083):** the progress numbers equal the ExecutionSummary counts
(counts by status over non-superseded runs); folder and assignee breakdowns sum to the total.

### R-084 · Cycle lifecycle: start, close, reopen, clone, archive (US-084)
**Refs:** FR-EXE-012, BR-11 · **Tests:** TCMS-058, TCMS-059, TCMS-060

As a QA Lead, I move a cycle through `planned → active → closed`, and `closed → active` via reopen.

- **Start** (`cycle.manage`): `planned → active`. Also automatic on first execution (BR-30 — the automatic
  trigger lands with the runner in M4; the explicit start endpoint is M3).
- **Close** (`cycle.manage`): draft attempts must be finalized or discarded first; `409` lists the drafts
  when any exist and `discard_drafts` is not set. Not-run runs remain not run. Sets `closed_at`,
  `closed_by`. *(Draft attempts only exist once the runner exists in M4; in M3 the close path handles the
  no-drafts case and the drafts-listing contract so M4 slots in without changes.)*
- **Reopen** (`cycle.reopen`): reason required (`422` without it); `403` without the permission; status
  → `active`.
- **Clone** (`cycle.manage`): new cycle with the same cases at **current** eligible versions, no results;
  option `only_statuses` ∈ {`failed`, `blocked`, `not_run`} to carry only those runs for re-test rounds.
- **Archive** (`cycle.manage`): closed cycles only; hidden from default lists; still in reports.

BR-11: in a closed cycle, assignments cannot change and (once M4 exists) no attempts can start or finalize.

**Acceptance (docs/08):** TCMS-058 — closing a cycle with drafts lists them and offers a discard option;
TCMS-059 — reopen without permission → `403`, without reason → `422`, otherwise success; TCMS-060 — clone
with `only_statuses` carries the correct subset at current versions.

### R-085 · Sync a cycle from its plan (US-085)
**Refs:** BR-31 · **Tests:** AC-PLN-02 / TCMS-053

As a QA Lead, I sync a cycle with its plan. "Sync from plan" adds plan cases not yet in the cycle and
**never removes** runs with results (BR-31). Permission `cycle.manage`.

**Acceptance (docs/02 AC-PLN-02, verbatim):** Given a cycle created from a plan, when 10 cases are added to
the plan, then the cycle is unchanged until "Sync from plan" is run, which adds 10 runs.
**Also (docs/08 TCMS-053):** sync adds only new cases; no runs are removed.

### R-086 · Update-to-latest and replace-run (US-086)
**Refs:** FR-EXE-011, BR-04, BR-05 · **Tests:** — (TCMS-082/083 full in M4; M3 builds the version actions)

As a QA Lead, I update not-run runs to the latest eligible version or replace runs that have results.

- **Update to latest** (`cycle.manage`, or the assignee with `run.execute`): allowed only when the run has
  no attempts (BR-04); `409 already_latest` if already on the eligible version. Bulk: "Update all not-run
  runs in this cycle".
- **Replace run** (`cycle.manage`): run has ≥1 finalized attempt and is not superseded; creates a new run
  (same position, same assignee) at the latest eligible version; old run `superseded_by_run_id = new`,
  keeps its results, excluded from metrics (BR-05). Superseded runs appear only with `include_superseded`.

*(Replace-run requires a finalized attempt to exist, which is M4. In M3 the endpoint, rules and the
superseded bookkeeping are built and unit-tested against seeded finalized results; the end-to-end
retest-round journey is exercised in M4.)*

**Acceptance (docs/02 §7.2, BR-04/BR-05):** update-to-latest on a run with attempts is refused; on a
not-run run it re-pins the eligible version; replace-run supersedes the old run (old keeps results, new is
not_run at latest), and the old run is hidden unless `include_superseded`.

### R-087 · Reorder runs (US-087)
**Refs:** docs/02 §7.1 · **Tests:** —

As a QA Lead, I reorder runs in a cycle by drag or by "sort by folder/priority". Default order is folder
tree order then case key. `position` is persisted. Permission `cycle.manage`.

**Acceptance (docs/02 §7.1):** reordering persists `position`; "sort by folder/priority" reorders all
non-superseded runs deterministically.

---

## Out of scope for M3 (tracked for later)

- Recording step results, draft/final attempts, finalize + roll-up, retest, correction, evidence, the
  runner UI, My Work, automatic start-on-execute (BR-30 trigger) — **M4** (FR-EXE-005…010/014, BR-06…10/30/32).
- Requirements coverage / RTM for linked requirements — **M6**.
- Readiness evaluation of a plan's `exit_rules` — **M7** (the rules are stored and validated in M3).
