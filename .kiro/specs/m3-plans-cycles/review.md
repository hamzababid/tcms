# M3 review against docs/ (2026-11-05)

Review of the M3 spec in this folder and of the code on `milestone/m3-plans-cycles` against
docs/02, 04, 05, 06, 07, 08 and docs/design. M1 and M2 are the quality bar. Every item below is fixed
in the rework tasks (tasks.md §8) unless marked otherwise.

## 1. Spec defects (this folder)

| # | Where | Problem | Correct source |
| --- | --- | --- | --- |
| S1 | design.md §4.2 | Run action shapes were guessed. docs/06 §4.6 fixes them: assign takes `{run_ids? \| filter?, assignee_id \| null}`; reorder takes `{run_ids_in_order}` or `{sort_by}` | docs/06 §4.6 |
| S2 | design.md §4.2 | `GET /runs/{id}` (run, case summary, pinned version, newer version info, history) is missing | docs/06 §4.6, §5.4 |
| S3 | design.md §4.2 | Cycle read shape not taken from docs/06 §5.3 (release/plan/environment refs, `summary` = ExecutionSummary §5.7) | docs/06 §5.3, §5.7 |
| S4 | design.md §5 | Audit actions invented as `test_plan.*`, `test_cycle.*`, `run.claimed`, `run.reordered`. docs/02 §13.1 says `plan.*`, `cycle.created/updated/started/closed/reopened`, `run.added/removed/assigned/version_updated/replaced`, `result.discarded` | docs/02 §13.1 |
| S5 | design.md §3.2 | One `run.added` event per cycle. docs/04 §5.2 requires one event per run with a shared `bulk_operation_id` | docs/04 §5.2 |
| S6 | requirements.md R-070 | Exit rules modelled as `{metric, operator, threshold}`. docs/02 §11.4 defines rule types (`min_execution_progress`, `max_open_defects`, …) and docs/06 §5.9 the `{type, threshold, params}` shape | docs/02 §11.4 |
| S7 | requirements.md | Project archive "all cycles must be Closed (or the dialog offers to close them)" (US-029 tail, review K17k) was listed in tasks but never implemented | docs/02 §4.2 |
| S8 | tasks.md §5 | Frontend tasks did not list the screens of docs/07 §5.7–5.8 (plan form, plan tabs, add-cases dialog, stepped create-cycle dialog, cycle detail per docs/design/CycleDetail) | docs/07 |
| S9 | tasks.md §6 | E2E coverage did not follow docs/08 levels: TCMS-050, 055, 058 are level E | docs/08 §15.4 |

## 2. Backend deviations

| # | Area | Deviation |
| --- | --- | --- |
| B1 | Cycle read/list | `summary` was `{total, by_status}`; must be ExecutionSummary with rates as `{numerator, denominator, value}`, computed in `reporting/metrics.py` (CLAUDE.md rule 5) |
| B2 | Cycle read | No release/plan/environment refs, no progress by folder (FR-EXE-013, US-083), no closed by/at |
| B3 | Create cycle | Response was `{cycle_id, key, …}`; docs/06: `201 {cycle, added, skipped[]}` or `202` |
| B4 | Selection | `priorities` ignored; `from_plan` with folder/tag filters added cases instead of narrowing the plan's cases |
| B5 | Positions | Runs were positioned in selection order; docs/02 §7.1 default is folder tree order, then case key |
| B6 | Reorder | `sort_by=priority` sorted by folder; body key `ordered_run_ids` instead of `run_ids_in_order` |
| B7 | Runs list | Filters `folder_id`, `priority`, `tag`, `q` and sorts `key`, `priority` missing; two extra queries per row |
| B8 | Assign | No `filter` form (TCMS-055 "bulk assign by folder") |
| B9 | Close | `discard_drafts=true` closed the cycle but left the drafts in place; the 409 only listed run ids |
| B10 | Update versions (bulk) | One run without an eligible version aborted the whole batch |
| B11 | `GET /runs/{id}` | Missing (newer-version banner "v5 available (you are on v3)" has no data source) |
| B12 | Plan cases | "Latest result in each linked cycle" used every cycle of the case, not the plan's cycles; N+1 queries |
| B13 | Plan detail | `?include=cases,requirements,cycles` not supported |
| B14 | Resolve | `GET /projects/{pid}/resolve` does not resolve `PL`/`CY` keys; the web resolved keys by searching the list |
| B15 | Audit | See S4/S5 |
| B16 | Project archive | Open cycles not checked (S7) |
| B17 | Clone | `only_statuses` accepted any run status; docs/06: `failed, blocked, not_run` |

## 3. Frontend deviations (docs/07 §5.7–5.8, docs/design/CycleDetail.dc.html)

- Plans: no plan form (objectives, scope, environments, entry/exit criteria with rule editor, risks, dates, owner, members, release); no tabs (Overview, Cases, Cycles, History); no "Add cases" dialog; no case removal; list filters not wired.
- Cycles list: status as plain text (StatusBadge is the single status source), no progress, no filters beyond status.
- Create cycle: only name, environment and plan; no release/build/dates, no repository selection or plan filters, no default assignee, skipped cases with reasons never shown (AC-PLN-01).
- Cycle detail: no header meta line, progress section per design, group by assignee/folder, run filters, bulk selection and assign, add/remove runs, update-to-latest, replace, reorder, clone, archive, edit, closed banner, run side panel with the newer-version banner, superseded toggle.
- Errors from mutations were swallowed (`void promise.then(...)` without error handling).
- Keys resolved through list search instead of `/resolve` (docs/04 §11.1).

## 4. Out of scope for M3 (unchanged)

Recording/finalizing attempts, the runner, "Start testing", BR-30 auto-start, My Work (M4); defects column (M5); requirements tab and saved views (M6); readiness evaluation of exit rules (M7); export (M8).
