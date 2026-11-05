# M4 — Execution runner · Requirements

| Field | Value |
| --- | --- |
| Milestone | M4 (docs/09 §2): "Testers can execute a cycle" |
| Epic | E09 Execution (docs/10): US-090…US-100 |
| Source of truth | docs/02 §7.3–7.5; docs/01 §7 (BR-06…10, BR-30, BR-32); docs/06 §4.1 (`/me/work`), §4.7, §5.4–5.5, §6; docs/05 §3.5 + `01_baseline.sql` (`test_results`, `test_step_results`, triggers); docs/04 §5.3–5.6, §10.2, §11.5; docs/07 §5.9, §5.14; docs/design/Runner.dc.html; docs/08 §6.1, §10, §15.5 (TCMS-070…090) |
| Review items due | K2, K17h, K17i (docs/ops/00-review.md); K5 (landing → My Work) |
| Out of scope | Defects (raise/link, `defect-draft`, `require_defect_for_failure`, retest prompts BR-22, linked-defect chips): M5. Saved views, global search: M6. Notification bell: M7. Automation results (`source = automation`): P2 |

## Business rules (docs/01 §7, verbatim)

- **BR-06** — A result attempt is **draft** while being executed and is editable only by its executor (or a user with `cycle.manage`). Once **finalized** it is immutable.
- **BR-07** — A run has at most one draft attempt at a time.
- **BR-08** — Run status = status of the latest finalized attempt; `in_progress` if a draft attempt exists; `not_run` if no attempt exists.
- **BR-09** — Finalized status of a Steps attempt: Failed if any step Failed; else Blocked if any step Blocked; else Passed if every step is Passed or Skipped and at least one Passed; otherwise the tester must choose Blocked, Skipped or Not Applicable with a reason. A Text attempt's status is chosen by the tester.
- **BR-10** — Blocked, Skipped and Not Applicable as run-level outcomes require a reason. A Failed step requires an actual result. *(Decision D1: "run-level outcome" includes a Blocked derived from steps.)*
- **BR-30** — Executing a run in a Planned cycle moves the cycle to Active.
- **BR-32** — When a run is executed by someone other than its assignee, `executed_by` records the actual user; if the project enables "only assignee executes", others are blocked unless they hold `cycle.manage`.

## AC (docs/02 §7.3, verbatim)

- **AC-EXE-01** — Given a draft with steps [passed, failed, not_run], when finalized, then status = failed.
- **AC-EXE-02** — Given a draft with steps [passed, skipped, passed], when finalized, then status = passed and skipped_steps = 1.
- **AC-EXE-03** — Given a draft with steps [passed, not_run], when finalized without outcome, then `422 incomplete_attempt`.
- **AC-EXE-04** — Given a finalized attempt, when any update to it or its step results is attempted (API or SQL as app user), then it is rejected.
- **AC-EXE-05** — Given a run with a draft by user A, when user B (no cycle.manage) starts an attempt, then `409 draft_exists`.
- **AC-EXE-06** — Given a closed cycle, when an attempt is started, then `409 cycle_closed`.
- **AC-EXE-07** — Given a run with a failed final attempt, when a retest passes, then run status = passed, attempt history shows both, and metrics count the run as passed.
- **AC-EXE-08** — Given a case edited to v4 while a run is pinned to v3 with a result, then the run still displays v3 steps, and "Update to latest" is disabled with tooltip "Run has results — use Replace run".
- **AC-EXE-09** — Given 50 testers saving step results concurrently on different runs, then no update is lost and p95 save latency < 200 ms.

---

### R-090 · Start an attempt and record steps with auto-save (US-090)
**Refs:** FR-EXE-005/006, BR-06/07/30/32 · **Tests:** TCMS-070, 077, 078, 084, 085, AC-EXE-05/06/09

`POST /runs/{id}/results {take_over?, corrects_result_id?}` (`run.execute`). Cycle not closed (`409 cycle_closed`), run not superseded (`409 run_superseded`). BR-32: with `only_assignee_executes`, a non-assignee without `cycle.manage` gets `403 not_assignee`. If the caller already owns the draft, it is returned (idempotent). A draft by someone else → `409 draft_exists` (body names the executor) unless the caller holds `cycle.manage` and sends `take_over: true` (`result.draft_taken_over`). Otherwise a draft is created with `attempt_no = max + 1`, `build` and `environment_id` copied from the cycle, one `not_run` step row per step of the pinned version (steps format); run → `in_progress`; a planned cycle → active (BR-30, `cycle.started`). Audit `result.started`.

`PATCH /results/{id}/steps/{step_id} {status?, actual_result?, comment?}` by the executor or `cycle.manage`; draft only (`409 immutable_record` when final). No audit per step (docs/04 §5.4). `PATCH /results/{id} {comment?, build?, duration_seconds?}`. `POST /results/{id}/steps/bulk {status: passed, only_not_run: true}` ("Pass all remaining"). Step saves meet AC-EXE-09.

### R-091 · Derived status on finish (US-091)
**Refs:** FR-EXE-007, BR-08/09 · **Tests:** TCMS-071 (exhaustive matrix), 073, 075, AC-EXE-01/02/03

`POST /results/{id}/finalize {outcome?, reason?, duration_seconds?}`. Status per BR-09 and the docs/02 §7.3 precedence table (with D1/D2). Failed steps without actual result → `422 actual_result_required` listing step positions (TCMS-072). Finalize sets `state = final`, `status`, `finished_at`, `duration_seconds` (body, else elapsed, capped 86,400), `skipped_steps`; run `status`, `latest_result_id`, `needs_retest = false`. Audit `result.finalized` (or `result.corrected`). Concurrent finalizes of one draft: exactly one succeeds (TCMS-090).

### R-092 · Block / skip / N/A a run with a reason (US-092)
**Refs:** FR-EXE-008, BR-10 · **Tests:** TCMS-074

Explicit `outcome` ∈ {blocked, skipped, not_applicable} requires `reason` (≤ 1,000) → `422 reason_required`. Allowed per the precedence table; never against a failed step (`422 outcome_conflicts_with_steps`).

### R-093 · Evidence per step (US-093)
**Refs:** FR-EXE-006, BR-28 · **Tests:** TCMS-087

Attachments with `entity_type = test_step_result` (the step row of a draft). Upload/unlink by the executor or `cycle.manage` while the attempt is a draft; final attempts → `409 immutable_record`. Paste into actual result/comment uploads the image. Discarding a draft removes its evidence (soft-delete for GC).

### R-094 · Keyboard and next run (US-094)
**Refs:** NFR-UX-01, docs/02 §7.4 · **Tests:** TCMS-086, 088

Runner keys: `P/F/B/S` step status (`F` focuses actual result), `↓/J`, `↑/K`, `Space` start, `A` attach, `Ctrl+Enter` finish, `Shift+N` next run, `?` help. Queue = cycle runs assigned to me and not finalized, by position (all not-finalized runs when none are mine); "Mine / All" and "Not done / All" toggles. After finishing: toast with result and next run; auto-advance after 1 s. Save indicator per step; failed saves retry every 5 s; Finish disabled until saves succeed. "Pass all remaining" (confirm when > 10 steps). Timer from start.

### R-095 · Retest (US-095)
**Refs:** FR-EXE-009 · **Tests:** TCMS-079, AC-EXE-07

"Retest" on a run with a final attempt starts attempt n + 1; history lists every attempt; metrics use the latest final attempt.

### R-096 · Correct a result (US-096)
**Refs:** FR-EXE-010 · **Tests:** TCMS-080

"Correct result…" on the latest final attempt starts an attempt with `corrects_result_id`; allowed for `cycle.manage` or the original executor while the cycle is not closed. Finalize requires `reason`; audit `result.corrected`. The corrected attempt shows struck through with a link.

### R-097 · Immutability and one draft (US-097)
**Refs:** BR-06/07 · **Tests:** TCMS-076 (API + SQL), 077, 090, AC-EXE-04/05

Final attempts and their step rows reject every API change (`409 immutable_record`) and SQL changes as `tcms_app` (trigger). The partial unique index guarantees one draft; concurrent starts produce one draft.

### R-098 · Text-format cases (US-098)
**Refs:** docs/02 §7.3 · **Tests:** TCMS-089

No step rows; the tester chooses `outcome` ∈ {passed, failed, blocked, skipped, not_applicable} (`422 outcome_required` without one); `failed` requires `comment` (`422 field_required`); blocked/skipped/N/A require `reason`.

### R-099 · My Work (US-099)
**Refs:** FR-EXE-014, docs/02 §7.5, docs/07 §5.14 · **Tests:** US-099 API test, E2E

`GET /me/work`: runs assigned to me in planned and active cycles of active projects I belong to, grouped by cycle (project, cycle key/name, due date, counts by status, needs-retest count, next run), plus cases awaiting my review and my last-7-days execution counts. Landing page becomes My Work (review K5; TCMS-001 expectation updated).

### R-100 · Newer version in the runner (US-100)
**Refs:** BR-04, AC-EXE-08 · **Tests:** TCMS-081, 082

The runner shows the pinned version's steps; banner "v4 available (you are on v3)" with Update when allowed (no attempts) and "Run has results — use Replace run" otherwise.

### Completed tails from M3

- Close a cycle with live drafts end-to-end (L22) — E2E.
- Replace run after a result (BR-05, L21) — E2E (TCMS-083).
- BR-30 auto-start (L23) and "Start testing" on the cycle (L23).
