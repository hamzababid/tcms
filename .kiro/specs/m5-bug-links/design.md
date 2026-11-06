# M5 — Bug links · Design

## 1. Decisions

**(Q)** = needs the product owner's answer before building; the rest are my calls and can be overridden.

| # | Topic | Decision | Why |
| --- | --- | --- | --- |
| D1 | Scope | Bugs stay in the team's tracker. Assay stores bug links only: no status, assignee, severity, workflow, watchers, kanban or notifications. New ADR in docs/11 ("Bugs live in the team's tracker; Assay links to them"); PRD FR-DEF, BR-19…22, UJ-6, MVP gate, RK-04 and AS-02 updated | Product owner, 2026-11-06 |
| D2 | Storage | New table `bug_links` (migration + `docs/schema/04_m5_bug_links.sql`): `id, organization_id, project_id, reference (1–100), reference_norm (upper-cased, trimmed), url (≤ 2,000, http/https), title (≤ 255), test_case_id NOT NULL, run_id, result_id, step_id, created_at, created_by, updated_at, updated_by`. CHECK `(result_id IS NULL) = (run_id IS NULL)`; composite FKs to project; unique `(project_id, reference_norm, test_case_id, coalesce(result_id, nil), coalesce(step_id, nil))`; indexes on `(project_id, reference_norm)`, `run_id`, `result_id`, `test_case_id`. Every link carries its case, so case views need no joins through runs | docs/05 §4 tenancy rules |
| D3 | Old defect tables | `defects`, `defect_links`, `defect_status_history`, `defect_watchers` stay in the schema, unused (no data, reserved for a future tracker connector). Dropping baseline tables is avoidable churn; docs/05 marks them "not used in MVP". `defects/models.py` is kept; the new code lives in a `bugs` module | Reversible, smallest change |
| D4 | Module and layering | New module `tcms.bugs` between `reporting` and `execution` in the import-linter layers (it replaces `defects` there; private models/repository contract). It reads execution and testdesign through their public queries and calls `execution.service.flag_runs_for_retest` | CLAUDE.md layering |
| D5 | Permissions | Reuse the existing codes so role seeds don't change: `defect.create` = "Link bugs" (QA Manager, Lead, Engineer, Developer); `defect.edit` = "Edit or remove any bug link" (the creator can always edit/remove their own). "Ready for retest" needs `cycle.manage`. `defect.transition.any/dev/verify` remain in the catalog unused (documented) | docs/02 §3.1–3.2 |
| D6 | `require_bug_link_for_failure` across layers | `execution` is below `bugs`. Finalize emits `ResultFinalizing(result_id, status, project_id)` and dispatches it at once; the `bugs` handler raises `422 bug_link_required` when the setting is on, the status is `failed`, and the attempt has no link. Setting key renamed from `require_defect_for_failure` (value carried over by the migration) | docs/03 §5.4 in-tx handlers (K13) |
| D7 | Discarding a draft | `DraftDiscarding(result_id)` is dispatched before the delete (also when closing a cycle with drafts); the handler deletes that attempt's links and audits `bug.unlinked` (reason "draft discarded") | FK on `result_id` |
| D8 | Project settings | `bug_tracker_name` (1–40, default "tracker") and `bug_url_template` (optional, `http(s)://` with exactly one `{ref}`). The URL is built at creation and stored (changing the template later does not rewrite old links) | AC-BUG-02 |
| D9 | URL safety | Only `http`/`https` accepted and rendered; links open with `target="_blank" rel="noopener noreferrer"`; `{ref}` is URL-encoded when filling the template | AC-BUG-05 |
| D10 | Readiness rule `max_open_defects` (Q1, taken as proposed on "go ahead") | Assay cannot know whether a tracker bug is open. Replace it with **`max_failed`** ("Failed runs ≤ n", count rule) and migrate stored rules of type `max_open_defects` to `max_failed` with the same threshold (seed SPARK-PL-1 included). Alternative: delete the rule type and drop it from stored plans | docs/02 §11.4 |
| D11 | Retest | "Ready for retest" works per reference across the project (all eligible runs linked to it), with a preview count in the confirm dialog. Audit `bug.retest_requested` with the flagged run ids. No automatic flagging | BR-21 rewritten |
| D12 | "Copy bug details" | Client-side text built from `GET /results/{id}/bug-report?step_id=` (Markdown: case key + title, preconditions, steps 1..n of the pinned version with test data, expected, actual, environment, build, cycle, run URL). Saves the tester retyping in their tracker | Replaces the docs/06 `defect-draft` prefill |
| D13 | Traceability and reports | docs/02 §10 (RTM) shows "linked bugs" (references) per requirement instead of open defects by severity; the M7 defects report becomes a "bug links" report (reference, cases, runs, latest status of linked runs) | Follow-on docs only |

## 2. Backend

- `bugs/rules.py` (pure): `normalize_reference`, `validate_reference`, `validate_url` (http/https only), `validate_template` (one `{ref}`), `build_url(template, ref)`, `bug_report_text(context, step_position)`.
- `bugs/models.py`, `bugs/repository.py` (private); `bugs/service.py`: `add_link`, `update_link`, `remove_link`, `request_retest`, handlers `on_result_finalizing` (D6), `on_draft_discarding` (D7).
- `bugs/queries.py`: `links_for_runs(run_ids)`, `links_for_results(result_ids)`, `links_for_case(case_id)`, `bug_list(project, filters, page)` (grouped by `reference_norm`), `links_of_reference(project, ref)`, `bug_report(result_id, step_id)`, `owning_project_of_link`.
- `execution`: events `ResultFinalizing`, `DraftDiscarding`; `service.flag_runs_for_retest(uow, ctx, run_ids) -> list[UUID]`; queries `attempt_context(result_id)` for the report and validation.
- `workspace`: settings `bug_tracker_name`, `bug_url_template`, `require_bug_link_for_failure` (rename).
- `planning`: `max_failed` rule (D10 per Q1).

API (`api/v1/bugs.py`):

| Method | Path | Perm |
| --- | --- | --- |
| POST | `/results/{id}/bug-links` `{reference, url?, title?, step_id?}` | defect.create |
| POST | `/test-cases/{id}/bug-links` `{reference, url?, title?}` | defect.create |
| PATCH / DELETE | `/bug-links/{id}` `{url?, title?}` | creator or defect.edit |
| GET | `/projects/{project_id}/bugs` (`q`, `cycle_id`, `failing`, page) | project.view |
| GET | `/projects/{project_id}/bugs/links?reference=` → links | project.view |
| POST | `/projects/{project_id}/bugs/retest` `{reference, dry_run}` → `{reference, linked_runs, flagged, dry_run}` | cycle.manage |
| GET | `/results/{id}/bug-report?step_id=` | project.view |
| GET | `/test-cases/{id}/bug-links`, `/runs/{id}/bug-links`, `/cycles/{id}/bug-links?recent=` | project.view |

References travel in the query or body (they may contain `#` or `/`). Run and cycle reads fetch links from these endpoints instead of new fields on `RunRead`/`RunListItem` (keeps execution schemas free of a dependency on `bugs`). Authz matrix entries; `make api-client`.

## 3. Frontend (`features/bugs/`)

- `BugLinkPopover` (reference, URL prefilled from template, title, recent references), `BugChip` (opens the URL; menu: copy reference, edit, remove, Ready for retest), `CopyBugDetails` button.
- Runner: step action "Link bug (D)", chips per step and attempt, footer line, Finish opens the popover when a link is required.
- Run panel and history chips; cycle detail "Bugs" column and "⟳ n need retest" filter; case page "Bugs" tab; project "Bugs" page with list + detail drawer + Ready for retest confirm (shows the count).
- Project settings › Options: tracker name, URL template, "A failed result needs a bug link".
- Sidebar "Bugs" and `G D` (docs/07 shortcut kept).

## 4. Testing

- Unit `test_bug_rules.py`: reference/URL/template validation, URL building and encoding, bug report text.
- API `test_bug_links.py`: AC-BUG-01…06, TCMS-101/102/105/107, permissions, tenancy (other project's ids → 404), discard removes links (D7), final attempts accept links (BR-20), settings validation.
- Integration: TCMS-103 (BR-21 eligibility), finalize with the setting (TCMS-106) including the concurrent "link then finalize" order.
- Authz matrix for every new route; `br_manifest.COMPLETED` adds M5 (BR-20, BR-21); retired BRs removed from the manifest's MVP set.
- E2E `m5.spec.ts` with axe: TCMS-100 (keyboard link from the runner, chip in cycle and case), TCMS-104 (Ready for retest → ⟳ → retest clears it), TCMS-106 (required link on Finish), Bugs page filter, settings template.
