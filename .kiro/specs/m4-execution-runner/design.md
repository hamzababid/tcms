# M4 — Execution runner · Design

## 1. Decisions

| # | Topic | Decision | Source / why |
| --- | --- | --- | --- |
| D1 | K2: reason for a step-derived Blocked | **Every** final blocked / skipped / not_applicable attempt needs a reason, including Blocked derived from steps. Finalize returns `422 reason_required`; the runner asks for it before finishing | Storage wins (CHECK in `test_results`, asserted by `99_verify.sql`); review proposal Q2. docs/02 §7.3 table and docs/01 BR-10 wording updated |
| D2 | K17h/i: explicit outcome vs steps | Steps format: explicit `passed` or `failed` → `422 outcome_conflicts_with_steps`; any explicit outcome when a step failed → `422 outcome_conflicts_with_steps` (not silently "failed wins"). docs/04 §5.5 pseudocode fixed | Review K17h/i |
| D3 | `require_defect_for_failure` | Not enforced in M4: defects (and linking them to attempts) arrive in M5. The setting is stored; M5 adds the `422 defect_required` check. Recorded in known-limitations | docs/09: defects are M5 |
| D4 | Step evidence | Attachment entity `test_step_result` (row of the draft). Upload/unlink: executor or `cycle.manage`, draft only; final → `409 immutable_record` (BR-28). Discard removes links (orphans soft-deleted for GC). Run-level attachments are not offered (docs/07 attaches per step) | docs/04 §10.2, docs/06 §6 |
| D5 | Queue | `GET /runs/{id}?include=queue&queue_filter=mine_open\|mine\|open\|all` → `{position, total, previous_run_id, next_run_id}`; default `mine_open`, falling back to `open` when the caller has no assigned runs in the cycle. "Open" = not finalized (`not_run`, `in_progress`). The runner's left list uses the runs list with the same filter | docs/02 §7.4, docs/06 §4.6 |
| D6 | Correction | Allowed on the latest final attempt only, by `cycle.manage` or its executor, cycle not closed; reason required at finalize; audit `result.corrected` | docs/02 §7.3 |
| D7 | My Work | `GET /me/work` returns cycles with my runs (planned/active cycles, active projects), reviews awaiting me, my 7-day counts. Defects block comes with M5 (not rendered). Landing → `/my-work` (K5) | docs/06 §4.1, docs/07 §5.14 |
| D8 | Performance | AC-EXE-09 as a `timing` test: 50 threads save steps on 50 runs, no lost update, p95 < 200 ms on the test stack. The 100k-case large seed (TM-4) and the k6 staging scenario are deferred to M8 hardening and recorded | docs/08 §9; keeps M4 within scope |
| D9 | Duration | `duration_seconds` = body value, else `finished_at − started_at`, capped at 86,400 | docs/02 §7.3, SQL CHECK |
| D10 | Run status maintenance | Service sets `run.status` (in_progress on start, final status on finalize, latest final status on discard). `rules.derive_run_status(attempts)` exists and is unit-tested (docs/04 §5.6); the nightly `execution.verify_run_status` job is registered and logs mismatches | docs/04 §5.6 |

## 2. Backend

### 2.1 Rules (`execution/rules.py`, pure)

- `compute_final_status(fmt, steps, explicit) -> (status, skipped_steps)` per docs/02 §7.3 with D1/D2; raises `RuleViolation` subclasses (`incomplete_attempt`, `outcome_required`, `outcome_conflicts_with_steps`).
- `finalize_problems(fmt, steps[(position, status, actual_result)], status, reason, comment)` → `actual_result_required` (positions), `reason_required`, `field_required` (text failed comment).
- `derive_run_status(attempts)` (BR-08).
- `can_start(cycle_status, superseded)`, `executes_as(assignee_id, user_id, only_assignee, has_manage)` (BR-32).
- `duration(started, finished, given)` (D9).

### 2.2 Service (`execution/service.py`)

`start_attempt`, `update_attempt`, `record_step`, `pass_remaining`, `finalize_attempt`, `discard_attempt`, `result_record` (attachments). Locks: start → run `FOR UPDATE`; record/finalize/discard → result `FOR UPDATE` (+ run on finalize/discard). Concurrency: the partial unique index `ux_test_results__run_draft` backs BR-07; a lost race maps the IntegrityError to `409 draft_exists`. Finalize of an already final row → `409 immutable_record`.

Audit (docs/02 §13.1): `result.started`, `result.draft_taken_over`, `result.finalized`, `result.corrected`, `result.discarded` (with a summary of recorded steps), plus `cycle.started` on BR-30. Target `AuditTarget("test_result", id, "<cycle key> / <case key> #<n>")`.

### 2.3 Reads (`execution/queries.py`)

- `result_detail(result_id)` → attempt + step rows (with the pinned step's action/expected, position) + attachments per step.
- `run_detail` gains `draft_steps`, `queue`.
- `my_work(principal)` across the user's projects (org-scoped; membership-scoped project ids from identity queries).

### 2.4 API (docs/06 §4.7)

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/runs/{id}/results` | 201 new draft, 200 existing own draft |
| GET | `/results/{id}` | AttemptRead (docs/06 §5.5) with `steps[]` |
| PATCH | `/results/{id}` | comment, build, duration_seconds |
| PATCH | `/results/{id}/steps/{step_id}` | status, actual_result, comment → StepResultRead |
| POST | `/results/{id}/steps/bulk` | `{status: passed, only_not_run: true}` → `{count}` |
| POST | `/results/{id}/finalize` | → `{result, run}` |
| DELETE | `/results/{id}` | draft only → 204 |
| GET | `/me/work` | D7 |
| GET | `/runs/{id}?include=draft,history,version,queue` | draft now carries steps; `queue_filter` |

Runs list `status` accepts a comma list (`status=not_run,in_progress`, docs/06 §6).

## 3. Frontend

- Route `/p/$projectKey/cycles/$cycleKey/run/$runId` (docs/04 §11.1) — full-width runner per docs/design/Runner.dc.html: header (cycle, "Run n of N · my queue", Prev/Next, timer), queue list (Mine/All, Not done/All), case header (key, folder path, priority, pinned version + newer banner), preconditions/test data, step grid with P/F/B/S buttons, actual result (required on fail), comment, evidence (attach/paste), comment + build, "Pass all remaining", "Block run…/Skip…/N/A…", live result preview (same BR-09 logic, mirrored client-side for preview only; server decides), Finish (Ctrl+Enter), history line.
- Start / Retest / Correct result… / Take over / Discard draft.
- Save indicator per step (saved / saving / not saved – retrying every 5 s); Finish disabled while unsaved.
- Keyboard handler scoped to the runner; `?` help dialog.
- Cycle detail: "Start testing" opens the first run of my queue; run panel "Open in runner".
- `/my-work` page per docs/07 §5.14 (To execute, Awaiting my review, My week); `/` redirects there (K5). Sidebar "My Work".

## 4. Tests

- Unit: `tests/unit/test_execution_rules.py` — exhaustive roll-up matrix (TCMS-071: every combination of step statuses for 1–4 steps × explicit outcomes), finalize problems, derive_run_status, BR-32, duration.
- API: `tests/api/test_attempts.py` — TCMS-070, 072–085, 089, AC-EXE-01…08, BR-30, BR-32, take-over, discard, correction, retest, evidence, My Work, queue; authz matrix entries for every route.
- Integration: TCMS-076 SQL immutability as `tcms_app`; TCMS-090 concurrent finalize (20 threads) and concurrent start; AC-EXE-09 timing test.
- E2E `frontend/e2e/m4.spec.ts`: TCMS-070, 074, 079, 081, 086 (keyboard only), 087 (paste), 088 (save retry), 089 (text case), My Work, close-with-drafts, replace after result.
