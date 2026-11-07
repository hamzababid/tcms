# Implementation checklist

Status per story: ✅ done (acceptance automated and passing) · 🟡 partial · ⬜ not started. Test paths are relative to `backend/tests` or `frontend/`.

## M0 — Foundations (branch `milestone/m0-foundations`)

| Story | Status | Acceptance → tests | Notes / deferred |
| --- | --- | --- | --- |
| US-001 Start the full stack with one command | ✅ | `make up && make migrate && make seed`: 66 s for a no-cache rebuild (base images cached); web :5173, api :8000, Mailpit :8025 (ports configurable). E2E `e2e/smoke.spec.ts` runs against the stack | Seed has no steps until M1 (L3). MinIO image source changed (L1) |
| US-002 Errors are problem+json with a stable code | ✅ | `api/test_problems.py`: unknown route, validation error with field pointers, every `DomainError` subclass → status + code, `request_id`, 405, 500 without leaking details; E2E unknown route | — |
| US-003 DB enforces immutability | ✅ | `integration/test_immutability.py` (`test_br_06_final_result_immutable_sql`, `test_br_01_version_content_immutable_sql`, `test_br_01_approval_columns_settable_once`, `test_br_26_audit_append_only_sql`, `test_br_07_single_draft_per_run`); `integration/test_schema.py::test_verify_sql_passes_as_app_role` (99_verify 35/35) | — |
| US-004 Jobs run with retry and dead-letter | ✅ | `integration/test_jobs.py`: backoff then `dead`, permanent `failed`, unknown type, dedupe, stale requeue, SKIP LOCKED, scheduler once per period, admin retry (TCMS-139 backend part) | Admin UI for dead jobs: M8 |
| US-005 API client generated; CI fails on drift | ✅ | `make api-client-check` (CI job `openapi-drift`); verified failing after an unregenerated schema change | — |
| US-006 Module boundaries enforced | ✅ | `lint-imports` (11 contracts); `unit/test_module_boundaries.py` proves private-model and upward imports fail | — |

M0 acceptance (docs/09):

| Criterion | Evidence |
| --- | --- |
| `make up && make migrate && make seed` < 10 min on a clean machine | 66 s measured (see L6) |
| `alembic check` clean | `integration/test_schema.py::test_alembic_check_is_clean` |
| Migrated schema matches `01_baseline.sql` | `test_migrated_schema_matches_docs_baseline` (pg_dump diff) |
| `99_verify.sql` passes as `tcms_app` in CI | `test_verify_sql_passes_as_app_role`; also run manually on the compose DB: 35/35 |
| problem+json for unknown route | `api/test_problems.py::test_unknown_route_is_problem_json`, E2E |
| Job runs and retries in a test | `integration/test_jobs.py` |

Technical milestones: TM-1 ✅ (baseline schema, triggers, grants) · TM-3 ✅ (generated client + drift check).

Also delivered (E01 technical tasks): core primitives (settings, UoW with audit/events/jobs, errors, AccessContext, permission registry, UUIDv7, clock, pagination/filter/sort allow-lists, row_version, scoping), ORM models for all 50 tables, audit recorder, worker + scheduler + jobs retention, S3 storage primitives, health live/ready, CLI (`migrate`, `worker`, `seed`, `storage-init`, `openapi`), frontend shell, `StatusBadge`/`ProgressBar`/`Metric`, CI gates, BR manifest, coverage gate, Schemathesis contract test.

## M1 — Identity, access and workspace (branch `milestone/m1-identity-workspace`)

Backend tests are in `backend/tests/api/` unless noted; E2E in `frontend/e2e/m1.spec.ts`.

| Story | Status | Acceptance → tests | Notes / deferred |
| --- | --- | --- | --- |
| US-010 Sign in with email and password | ✅ | AC-AUTH-01 `test_auth_smoke::test_member_signs_in_with_secure_cookies`, E2E TCMS-001; AC-AUTH-02 `test_tcms_002_…` (timing, serial) and `test_unknown_email_and_wrong_password_answer_identically` | — |
| US-011 Lockout | ✅ | AC-AUTH-03 `test_tcms_003_account_locks_after_ten_failures` (`auth.locked` audit, 423 after valid password, unlock after 15 min) | — |
| US-012 TOTP enrolment + recovery codes | ✅ | TCMS-005 `test_tcms_005_totp_sign_in_and_replay_rejected`; TCMS-006 `test_tcms_006_recovery_code_works_once`; 5 failures `test_five_mfa_failures_invalidate_pending_sign_in`; E2E enrolment (QR + secret, codes once, "I've saved these") | — |
| US-013 Admin forced MFA; MFA for all | ✅ | AC-AUTH-04 `test_tcms_004_…`, `test_mfa_policy_for_all_users`; E2E TCMS-004 | — |
| US-014 Password reset | ✅ | AC-AUTH-07 / TCMS-007 `test_tcms_007_…`, `test_reset_link_expires_after_60_minutes`, `test_password_policy_enforced`, `test_password_change_revokes_other_sessions` | — |
| US-015 Invitations | ✅ | TCMS-008 `test_tcms_008_…` + E2E; 7-day expiry; existing user → 409 `user_exists`; `accept_url` once (copy link) | Minimal Admin › Invitations screen (Q4) |
| US-016 Sessions: idle/absolute timeout, sign out, revoke | ✅ | AC-AUTH-06 / TCMS-009 `test_tcms_009_…`, `test_absolute_session_expiry`, `test_logout_and_session_revocation` | — |
| US-017 Personal API tokens | ✅ | TCMS-010 `test_tcms_010_read_token_cannot_write`, `test_project_restricted_token` | — |
| US-018 Permission resolution, seeded roles, authz matrix | ✅ | TCMS-012 `test_authz_matrix.py` (every route × 6 roles, non-member, other-org admin, org admin; guard on all OpenAPI operations); `unit/test_identity_rules.py` | — |
| US-019 Non-members 404, tenant isolation | ✅ | TCMS-013 `test_tcms_013_cross_tenant_and_non_member_access_is_404` | — |
| US-020 `tcms bootstrap` | ✅ | Verified on the stack (prints setup link); `World.org()` uses the same service | — |
| US-021 Organization settings and security policy | ✅ | `test_organization_settings_validation`, `unit/test_workspace_rules.py`; Admin › Security policy screen | — |
| US-022 Create project | ✅ | AC-WS-01 / TCMS-020/021 `test_tcms_020_…`, `test_br_27_project_key_format`, `test_tcms_021_…`; E2E TCMS-020 | Creator QA Manager; QA + Staging; key sequences; system tags |
| US-023 Project options | ✅ | `test_project_settings_validation_and_audit` (K9 cap, `project.settings_changed`) | Effects of the options arrive with their features (M2–M4) |
| US-024 Members and roles | ✅ | TCMS-023 / BR-29 `test_br_29_new_member_defaults_to_viewer`, `test_last_qa_manager_cannot_be_removed_or_demoted`; E2E (add member → Viewer) | New `GET /projects/{id}/member-candidates` (docs/06) |
| US-025 Environments | ✅ | AC-WS-03 part / TCMS-025a `test_tcms_025a_…` | TCMS-025b (cycle creation 422) in M3 |
| US-026 Releases and status | ✅ | TCMS-024 `test_tcms_024_release_status_transitions`, `unit/test_workspace_rules.py::test_release_transition_matrix` | Readiness/decisions: M7 |
| US-027 Shell, project switcher, breadcrumbs, collapse | ✅ | E2E TCMS-001/020 (navigation, axe on every visited screen) | Only built screens appear in navigation |
| US-028 Activity feed | ✅ | `test_us_028_activity_feed`; E2E TCMS-020 | — |
| US-029 Archive / restore project | ✅ | AC-WS-02 / TCMS-022 `test_tcms_022_archived_project_is_read_only` | "All cycles closed" check arrives with cycles (M3) |
| US-160 Audit in the same transaction | ✅ | `integration/test_uow.py` (M0), audit assertions across M1 tests | — |
| US-161 Record history (API) | ✅ | `test_us_161_record_history` | History tabs arrive with entity screens (M2+) |
| US-164 User administration (API) | ✅ | TCMS-011 `test_tcms_011_…`, `test_last_org_admin_is_protected`, `test_admin_resets_user_mfa` | Users screen: M8 |

Also: `project.admin_accessed` audited once per session (`test_org_admin_sees_every_project_and_access_is_audited_once_per_session`); CSRF (TCMS-014) and Origin checks; auth rate limit (`test_auth_rate_limit`); BR-16 key allocation (`test_br_16_…`); BR-25 (`test_br_25_stale_row_version`). Migration 0002 (`docs/schema/03_m1_additions.sql`) passes the schema diff and `99_verify.sql`. Seed `dev`/`e2e` profiles. Deferred items: see known-limitations L8–L12.

## M2 — Repository and test cases (branch `milestone/m2-repository-cases`)

| Story | Status | Verified by | Notes |
| --- | --- | --- | --- |
| US-040 Create, rename, reorder folders | ✅ | `test_br_15_folder_names_unique_among_siblings`, `test_tcms_030_…`; `unit/test_testdesign_rules.py` | Reorder: folder menu Move up/down and Alt+↑/↓ |
| US-041 Move folders (drag and drop) | ✅ | AC-TD-01/02 / TCMS-031 `test_tcms_031_folder_cycle_and_depth` (whole subtree checked); E2E TCMS-030 (drag) | Confirmation when moving > 100 cases |
| US-042 Archive/restore, delete empty folders | ✅ | AC-TD-03 / TCMS-032 `test_br_15_delete_folder_only_when_empty`, `test_folder_archive_hides_subtree` | — |
| US-043 Tree with counts, case list with filters | ✅ | TCMS-030 counts incl. descendants; filters/sort/search in `test_bulk_small_…`, `test_tags_…`, `test_resolve_key_and_search`, `test_br_13_…` | Speed on 2,000 folders not measured (L14) |
| US-044 Bulk operations | ✅ | TCMS-043 `test_tcms_043_bulk_move_300_runs_as_job` (202, job, 300 audit events with one bulk id); `test_bulk_small_runs_inline_…`, `test_bulk_by_filter_and_skips` | "Select all matching" uses the filter; completion not shown in UI (L15) |
| US-045 Tags incl. system tags | ✅ | `test_tags_system_and_custom` | Free tags are created on first use (FR-TD-008) |
| US-050 Steps-format case, step grid | ✅ | TCMS-033 `test_br_16_tcms_033_…`; E2E TCMS-033 + TCMS-046 (10 steps from the keyboard) | Enter / Tab / Alt+↑↓ / Ctrl+D / Ctrl+⌫ (undo) / paste rows |
| US-051 Text-format case | ✅ | `test_create_case_validation` | — |
| US-052 Content → new version; metadata → audit only | ✅ | BR-01/02, AC-TD-10/11/13 / TCMS-034/035 `test_br_01_tcms_034_…` (×2), `test_tcms_035_…` | Approval banner in the editor |
| US-053 Version history and compare | ✅ | AC-TD-12 / TCMS-036 `test_tcms_036_compare_versions` + E2E | Word diff, unchanged steps collapsed |
| US-054 Restore an older version | ✅ | TCMS-037 `test_tcms_037_restore_earlier_version` | — |
| US-055 Attachments on cases and steps; paste images | ✅ | `test_attachments_upload_download_unlink`, `test_attachment_permissions`, TCMS-045 / BR-28 `test_br_28_tcms_045_…` | Type sniffed, sandboxed download; paste needs a saved case (L18) |
| US-056 Comments and @mentions | ✅ | `test_comments_mentions_edit_window` | Mention format in docs/06 §4.12; bell in M7 (L16) |
| US-057 Related cases, duplicate | ✅ | TCMS-044 `test_tcms_044_duplicate_case`, `test_related_links` | — |
| US-058 Executions and history | ✅ | `test_br_14_tcms_042_…` (execution row), `test_case_history_lists_audit` | Executions fill from M3/M4 |
| US-059 Conflicting edits | ✅ | BR-25 `test_br_25_stale_content_save_conflicts`; E2E TCMS-047 (conflict dialog) | The editor pins the version it loaded |
| US-060 Automation status and keys | ✅ | `test_us_060_automation_keys_unique_per_project` | — |
| US-065 Submit for review | ✅ | TCMS-038 `test_br_17_tcms_038_approval_workflow` + E2E | Reviewer picker lists members who can approve |
| US-066 Approve / return with comments | ✅ | AC-TD-20/21/22 / TCMS-038/039 `test_br_17_…`, `test_br_18_tcms_039_self_approval_blocked`; E2E TCMS-038 | Review bar with changes since the approved version |
| US-067 Approval on/off handles existing cases | ✅ | TCMS-040 `test_tcms_040_…` | — |
| US-068 Deprecate, archive, restore | ✅ | BR-13 / TCMS-041 `test_br_13_tcms_041_…` | Picker exclusion applies from M3 |
| US-069 Hard-delete a never-run case | ✅ | BR-14 / TCMS-042 `test_br_14_tcms_042_…` (`409 case_has_runs`); `test_delete_requires_testcase_delete` | Confirm by typing the key |

Also: `GET /projects/{id}/resolve` and `Idempotency-Key` on creates (`test_resolve_key_and_search`, `test_idempotency_key_replays_create`; L10/L11 resolved); authz matrix covers every new route (76 probes); non-member/other-org 404 (`test_non_member_gets_404`). Seed: SPARK repository (docs/ops/local-setup.md). Deferred items: known-limitations L14–L19.

## Design system pass (branch `feat/design-system`)

| Item | Status | Verified by |
| --- | --- | --- |
| Tokens for every value in docs/design (neutrals, control border, row rule, accent tints, danger, sidebar, elevation) | ✅ | `frontend/src/styles/tokens.css` |
| Inter / JetBrains Mono per Main.dc.html (type scale 24/20/16/14/13/12, antialiased; contextual "×" substitution off) | ✅ | Screenshots of every screen |
| Shell: dark sidebar with project switcher, 34 px nav items, chevron breadcrumbs, avatar menu | ✅ | E2E TCMS-001 (switcher, nav), axe on every screen |
| Page frame: white header bar + full-bleed panes (repository) or padded content | ✅ | Screenshots; E2E 15/15 |
| Components: buttons (primary/secondary/ghost/outline destructive/tint, 36/32/28), fields, select chevron, menus, dialogs, tabs with counts, tags, keycaps, status badges, data tables | ✅ | `make lint`, Vitest, E2E with axe |
| One `DataTable` for every table (repository cases, activity, case versions/executions/history, projects, members, environments, releases, invitations, sessions, API tokens): column filters, sorting, Columns menu, rows per page, pagination | ✅ | `DataTable.test.tsx`; screenshots of every screen and tab; E2E 15/15 |
| Full-width layouts: settings, profile and security policy as card grids with summary cards; create forms (invitation, API token, release) in dialogs; full-page case with a Properties side card | ✅ | Screenshots at 1440 px |
| Audit filters for Activity and case History (`action`, `occurred_at__gte/lte`, `q`; docs/06) | ✅ | `test_activity_and_history_filters` |

## Brand assets (branch `feat/brand-assets`)

| Item | Status | Verified by |
| --- | --- | --- |
| Favicon (.ico/.svg), Apple touch icon, web manifest (192/512), theme colour | ✅ | E2E `smoke.spec.ts` "brand assets … are served" |
| Logo on sign-in screens (light) and sidebar (on-dark; mark when collapsed) | ✅ | E2E smoke + TCMS-001 (logo image with alt "Assay"), screenshots |
| Logo header in HTML emails (PNG) | ✅ | `unit/test_email_render.py`; reset email checked in Mailpit |
| Single source `docs/brand`, copies in `frontend/public` kept identical | ✅ | `make brand-check` (part of `make lint` and CI) |

## Status after Kiro handoff (2026-11-05)

Verified by running the stack and the full gate set (see `docs/ops/HANDOFF-kiro.md` §2):
`make up/migrate/seed` ✅, schema verify **35/35** as `tcms_app`, backend **320 passed** + 98 subtests +
1 timing, frontend **26 passed**, E2E **15 passed**, lint (ruff/format/mypy/import-linter 11 contracts/
eslint/tsc/prettier) ✅, brand + API-client drift ✅.

**Branch note:** the full M0–M2 + design-system + brand code lives on `feat/design-system`. `main`
(`5b58cd8`) still contains only M0 + M1 + the 2026-11-04 spec update; M2/brand/design were not
fast-forwarded onto it. Settle this (HANDOFF §5 D1) before branching M3.

## M3 — Plans and cycles (branch `milestone/m3-plans-cycles`)

Built by Kiro; reviewed against docs/ and reworked (`.kiro/specs/m3-plans-cycles/review.md`). Backend
tests in `backend/tests/api/test_planning.py` and `test_execution.py`; E2E in `frontend/e2e/m3.spec.ts`
(axe on every visited screen).

| Story | Status | Verified by | Notes |
| --- | --- | --- | --- |
| US-070 Create / edit a plan | ✅ | TCMS-050 `test_us_070_create_plan_with_exit_rules_and_risks`, `test_us_070_validation`, `test_us_070_exit_rules_are_validated_against_the_rule_types`, `test_us_070_status_lifecycle`; E2E TCMS-050 | Status machine draft → active → completed (docs/02 §6.1 lists no transitions; mirrors releases) |
| US-071 Add / remove plan cases | ✅ | TCMS-051 / BR-13 `test_br_13_us_071_add_cases_reports_exclusions`, `test_us_071_add_by_folder_and_remove`; E2E TCMS-051 | Saved views → 422 until M6 (L25) |
| US-072 Link requirements | ✅ (API) | `test_us_072_link_and_unlink_requirements` | Requirements tab in M6 (L25) |
| US-073 Clone a plan | ✅ | `test_us_073_clone_copies_everything_except_cycles` | — |
| US-074 Plan cases with results | ✅ | `test_us_074_plan_cases_list`, `test_us_074_plan_cases_show_results_of_the_plans_cycles_only`; E2E TCMS-053 (plan › Cycles) | — |
| US-080 Create a cycle | ✅ | AC-PLN-01 / TCMS-052 `test_br_03_br_12_ac_pln_01_create_cycle_from_plan`, `test_br_03_pins_the_approved_version_when_approval_is_enforced`, `test_selection_narrows_plan_cases_and_filters_priority`, TCMS-054 `test_tcms_054_…`, TCMS-025b `test_tcms_025b_…`; E2E AC-PLN-01 | Result shows skipped reasons after creating (L24) |
| US-081 Add / remove runs | ✅ | TCMS-057 `test_tcms_057_remove_run_with_results_refused`; E2E repository "Add to cycle" | — |
| US-082 Assign / claim | ✅ | TCMS-055 `test_tcms_055_bulk_assign_by_folder_notifies_the_assignee`, TCMS-056 `test_tcms_056_claim_a_pool_run`; E2E TCMS-055 + 056 | — |
| US-083 Cycle progress | ✅ | `test_us_083_summary_is_the_execution_summary_with_progress_groups`, BR-24 `test_empty_cycle_rates_are_undefined`, `test_runs_list_filters_and_sorts`, `unit/test_metrics.py`; E2E seeded demo (By assignee) | ExecutionSummary from `reporting/metrics.py` |
| US-084 Lifecycle: start, close, reopen, clone, archive | ✅ | TCMS-058 `test_tcms_058_…`, TCMS-059 `test_tcms_059_…`, BR-11 `test_br_11_closed_cycle_blocks_changes`, TCMS-060 `test_tcms_060_…`, `test_archive_needs_a_closed_cycle`; E2E TCMS-058 + 059 + 060 | Close with live drafts and BR-30 auto-start: done in M4 |
| US-085 Sync from plan | ✅ | BR-31 / AC-PLN-02 `test_br_31_ac_pln_02_sync_from_plan`; E2E TCMS-053 | — |
| US-086 Newer versions: update / replace | ✅ | BR-04 `test_br_04_update_to_latest_only_without_attempts`, `test_us_086_…` (2), BR-05 `test_br_05_replace_run_supersedes`, `test_get_run_includes`; E2E BR-04 (run panel) | Replace E2E added in M4 (TCMS-083) |
| US-087 Reorder runs | ✅ | `test_us_087_reorder_runs` | Sort by folder / priority in the UI; no drag (L27) |
| US-029 tail: archive needs closed cycles | ✅ | `test_us_029_archive_project_needs_closed_cycles` | Dialog offers to close them |

Also: audit names per docs/02 §13.1 (`test_audit_actions_follow_docs_02_13_1`; `cycle.archived` added
to §13.1); `/resolve` maps PL/CY keys (`test_resolve_plan_and_cycle_keys`); authz matrix covers every
M3 route; `br_manifest.COMPLETED` includes M3. Seed: SPARK-PL-1 and SPARK-CY-1. No migration (tables
existed). Deferred items: known-limitations L21–L27.

## M4 — Execution runner (branch `milestone/m4-execution-runner`)

Spec: `.kiro/specs/m4-execution-runner/`. Backend tests in `backend/tests/api/test_attempts.py`,
`tests/integration/test_attempt_concurrency.py` and `tests/unit/test_execution_rules.py`; E2E in
`frontend/e2e/m4.spec.ts` (axe on every visited screen). Review items K2, K17h, K17i and K5 are applied in
docs/01, 02, 04, 06 and 08 (decisions D1, D2, D7 in the spec).

| Story | Status | Verified by | Notes |
| --- | --- | --- | --- |
| US-090 Start an attempt, record steps, auto-save | ✅ | TCMS-070 / 084 `test_tcms_070_tcms_084_execute_a_run_all_passed`, `test_pass_all_remaining_marks_only_not_run_steps`, AC-EXE-09 `test_ac_exe_09_fifty_testers_save_steps_concurrently` (timing); E2E TCMS-070 + 086 + 084 | BR-30: the first start moves a planned cycle to active |
| US-091 Derived status on finish | ✅ | TCMS-071 `test_br_09_tcms_071_roll_up_matrix_is_exhaustive`, AC-EXE-01 / TCMS-072, AC-EXE-03 / TCMS-073, AC-EXE-02 / TCMS-075, K17h/i `test_k17h_k17i_…`; TCMS-090 `test_tcms_090_concurrent_finalize_exactly_one_succeeds`; E2E TCMS-072 | Bug-link rule for failures added in M5 (`require_bug_link_for_failure`) |
| US-092 Block / skip / N/A with a reason | ✅ | TCMS-074 `test_tcms_074_block_a_run_with_a_reason`, K2 `test_br_10_k2_blocked_from_steps_also_needs_a_reason`; E2E TCMS-074 | — |
| US-093 Evidence per step | ✅ | TCMS-087 `test_tcms_087_step_evidence_and_discard`; E2E TCMS-087 (paste) | Attempt-level attachments not offered (L29) |
| US-094 Keyboard and next run | ✅ | `test_runner_queue_is_my_open_runs_in_position_order`; E2E TCMS-086 (keyboard only), TCMS-088 (failed save), "Start testing" + Shift+N | — |
| US-095 Retest | ✅ | AC-EXE-07 / TCMS-079 `test_ac_exe_07_tcms_079_…`; E2E TCMS-079 + 081 | — |
| US-096 Correct a result | ✅ | TCMS-080 `test_tcms_080_correct_a_result_with_a_reason` | Latest final attempt only (D6) |
| US-097 Immutability and one draft | ✅ | BR-06 / AC-EXE-04 / TCMS-076 `test_br_06_…` (API + SQL trigger), BR-07 / AC-EXE-05 / TCMS-077 `test_br_07_…`, `test_br_07_concurrent_starts_make_one_draft`, AC-EXE-06 / TCMS-078 `test_ac_exe_06_…`, BR-32 / TCMS-085 `test_br_32_…`; E2E TCMS-058 with a live draft | — |
| US-098 Text-format cases | ✅ | TCMS-089 `test_tcms_089_text_format_case`, unit `test_tcms_089_…`; E2E TCMS-089 | — |
| US-099 My Work | ✅ | `test_us_099_my_work_lists_my_cycles_reviews_and_week`, `test_us_099_my_work_shows_cases_awaiting_my_review`; E2E TCMS-001 (lands on My Work), TCMS-070 | Defects block dropped by ADR-023 (bugs live in the tracker) |
| US-100 Newer version in the runner | ✅ | AC-EXE-08 / TCMS-081 / 082 `test_ac_exe_08_…`, TCMS-083 `test_tcms_083_…`; E2E TCMS-079 + 081, TCMS-083 (replace) | — |

Also: nightly `execution.verify_run_status` reports run-status mismatches without fixing them
(`test_run_status_consistency_check_reports_mismatches`); discarding a draft falls back to the latest final
status (`test_discard_falls_back_to_the_latest_final_status`); the authz matrix covers every M4 route;
`br_manifest.COMPLETED` includes M4. Seed: SPARK-CY-1 has 7 results and 1 draft by Sana. No migration
(tables existed). L12 and L21–L23 are closed; deferred items: known-limitations L14, L29–L31.

## M5 — Bug links (branch `milestone/m5-bug-links`)

Re-scoped by the product owner on 2026-11-06 (ADR-023): bugs live in each team's tracker (Jira, Azure DevOps,
GitHub, …); Assay records links to them. Spec: `.kiro/specs/m5-bug-links/`. Backend tests in
`backend/tests/api/test_bug_links.py` and `tests/unit/test_bug_rules.py`; E2E in `frontend/e2e/m5.spec.ts`
(axe on every visited screen). Migration `0003_m5_bug_links` (`docs/schema/04_m5_bug_links.sql`).

| Story | Status | Verified by | Notes |
| --- | --- | --- | --- |
| US-110 Link a bug from the runner | ✅ | AC-BUG-01/02 / TCMS-100 `test_ac_bug_01_02_tcms_100_link_from_a_failed_step`, BR-20 `test_br_20_final_attempts_accept_links_and_stay_immutable`; E2E TCMS-100 (keyboard `D`) | Final attempts accept links too |
| US-111 Tracker name and URL template | ✅ | `test_project_tracker_settings`, unit `test_ac_bug_02_template_builds_and_encodes_the_url`, `test_url_template_validation`; E2E project options | — |
| US-112 Chips on run, history, cycle, case | ✅ | `test_ac_bug_01_02_…` (run, cycle, case reads); E2E TCMS-100 | — |
| US-113 Link a bug to a case | ✅ | TCMS-102 `test_tcms_102_link_a_case_directly`; E2E TCMS-102 | — |
| US-114 Ready for retest | ✅ | BR-21 / AC-BUG-03 / TCMS-103 `test_br_21_ac_bug_03_tcms_103_…`; E2E TCMS-103 + 104 | Manual per reference (L32) |
| US-115 Copy bug details | ✅ | `test_copy_bug_details_report`, unit `test_bug_report_*` | — |
| US-116 Bugs list | ✅ | TCMS-105 `test_tcms_105_bugs_list_groups_by_reference`; E2E TCMS-105 | — |
| US-117 Failed result needs a bug link | ✅ | AC-BUG-04 / TCMS-106 `test_ac_bug_04_tcms_106_failed_result_needs_a_bug_link`; E2E TCMS-106 | Runner asks, then finishes |

Also: AC-BUG-05/06 `test_ac_bug_05_06_validation_and_duplicates`; TCMS-107 `test_tcms_107_edit_and_remove_permissions`;
discard and close remove a draft's links (`test_discarding_a_draft_removes_its_links`); tenancy
(`test_bug_links_are_project_scoped`); authz matrix covers every M5 route; `br_manifest`: BR-20/21 in M5, BR-19/22
retired; `max_failed` replaces `max_open_defects` (migrated). Seed: SPARK tracker "Jira", `SPK-431` on the failed
SPARK-CY-1 result, `SPK-440` on a case. L26 (Bugs column) and L28 are closed; deferred items: L32–L36.

## M6 — Requirement references, traceability, search (branch `milestone/m6-requirements-search`)

Re-scoped by the product owner on 2026-11-06 (ADR-024), like M5: requirements live in each team's tool; Assay stores
references to them, links them to cases and plans, and computes coverage, the matrix and status per release.
Spec: `.kiro/specs/m6-requirements-search/`. Backend tests in `backend/tests/api/test_requirements.py`,
`tests/api/test_search_views.py`, `tests/unit/test_requirement_rules.py`, `tests/integration/test_coverage_oracle.py`;
E2E in `frontend/e2e/m6.spec.ts` (axe on every visited screen). Migration `0004_m6_requirement_refs`
(`docs/schema/05_m6_requirement_refs.sql`).

| Story | Status | Verified by | Notes |
| --- | --- | --- | --- |
| US-120 Add references (paste many) | ✅ | AC-REQ-06 `test_ac_req_06_add_many_with_template_and_no_duplicates`, unit `test_paste_many`, `test_ref_problems`; E2E "Requirements page: paste many" | ≤ 500 per paste; replaces CSV import |
| US-121 Link from either side and in bulk | ✅ | TCMS-110 `test_tcms_110_link_from_either_side_and_in_bulk`, `test_us_072_plan_requirements_link_and_unlink`; E2E UJ-7 | Unknown references are registered (D12) |
| US-122 Coverage and status per release | ✅ | BR-23 / AC-REQ-01…05 / TCMS-111 `test_br_23_ac_req_01_to_05_tcms_111_status_per_release`, unit `test_br_23_status_in_release`, property test `test_br_23_coverage_sql_matches_the_python_oracle` | Scope rule Q1 = a |
| US-123 Traceability matrix | ✅ | TCMS-112 (E2E UJ-7), `test_traceability_shows_bugs_of_the_release` | Flat list, natural order; export in M8 |
| US-130 Global search | ✅ | AC-SRCH-01 / TCMS-118 `test_ac_srch_01_tcms_118_search_by_key`, TCMS-119 `test_tcms_119_search_by_text_grouped`, `test_tcms_119_search_is_fast` (timing); E2E TCMS-118 | Member projects only |
| US-131 Consistent filters | ✅ (partial) | Requirement filter on the repository (L19) via `test_tcms_110_…`; existing list filters | "is not"/"is empty" operators not on every list |
| US-132 Saved views and defaults | ✅ | TCMS-120 `test_tcms_120_saved_views_private_shared_and_defaults`, L25 `test_l25_add_plan_cases_from_a_saved_view`; E2E TCMS-120 | Column visibility not saved |
| US-133 Command palette | ✅ | E2E "TCMS-118 + palette" | `>` lists actions |

Also: edit/archive/restore and permissions `test_edit_archive_restore_and_permissions`; tenancy
`test_requirements_are_project_scoped`; authz matrix covers every M6 route (saved-view PATCH/DELETE are owner-only,
covered by TCMS-120); `br_manifest`: BR-23 in M6. Project setting "Requirement address" (`requirement_url_template`,
falls back to the bug address). Seed: SPK-101…105 on SPARK-PL-1 (SPK-105 has no case). L19, L25 and L34 are closed;
deferred items: L37–L42.

## M7 — Reporting, readiness and notifications (M7a `milestone/m7-reporting-readiness`, PR #14; M7b `milestone/m7b-notifications`)

M7 is delivered in two PRs (product owner, 2026-11-06): M7a reporting and readiness (E13), M7b
notifications and email (E16). Readiness is evaluated per plan (ADR-025, Q1 = a). Spec:
`.kiro/specs/m7-reporting-readiness/`. Backend tests in `backend/tests/api/test_reporting.py`,
`tests/unit/test_readiness_rules.py`, `tests/integration/test_metrics_oracle.py` (Hypothesis);
E2E in `frontend/e2e/m7.spec.ts` (axe on every visited screen). No migration (the baseline tables
`metric_snapshots`, `release_decisions`, `data_transfers` are used as designed).

| Story | Status | Verified by | Notes |
| --- | --- | --- | --- |
| US-140 One metrics module | ✅ | BR-24 / TCMS-113/114 `test_br_24_ac_rpt_01_02_tcms_113_114_summary_rates_and_superseded_runs`, property test `test_br_24_execution_summary_sql_matches_the_python_oracle` | `reporting/queries.py` scope shared by every screen |
| US-141 Manager dashboard (Overview) | ✅ | TCMS-115 `test_tcms_115_manager_dashboard_widgets`; E2E TCMS-115; timings in performance.md | `/p/:key`; filters release, environment, tester (L45) |
| US-142 Engineer dashboard (My Work) | ✅ | `test_us_099_my_work_lists_my_cycles_reviews_and_week` (today, attention); E2E "My Work lists my failed runs" | — |
| US-143 Quality trends from snapshots | ✅ | `test_quality_dashboard_trends_from_snapshots` | Snapshot job daily 00:15 UTC + Refresh |
| US-144 Six reports + CSV/XLSX | ✅ | `test_reports_filters_and_columns`, AC-RPT-05 / TCMS-117 `test_ac_rpt_05_tcms_117_export_escapes_formulas`, AC-RPT-04 `test_ac_rpt_04_large_export_runs_in_the_background`, unit escaping tests; E2E TCMS-117 | Closes L26 and the matrix part of L38 |
| US-145 Readiness and decision | ✅ | AC-REL-01…03 / TCMS-116 `test_ac_rel_01_*`, `test_ac_rel_02_*`, `test_ac_rel_03_*`, unit rule tests; E2E UJ-8 | Plan Overview readiness closes L25 |
| US-146 Organization dashboard | ✅ | `test_tcms_115_manager_dashboard_widgets` (org rows, member scoping) | `/org` |
| US-170 In-app notifications (bell) | ✅ M7b | AC-NTF-01 `test_ac_ntf_01_us_170_bell_count_list_and_mark_read`, L33 `test_l33_ready_for_retest_notifies_the_assignee`, purge `test_old_notifications_are_purged`, unit titles; E2E AC-NTF-01 | Closes L15, L16, the bell part of L20, L33 |
| US-171 Email: mentions, daily digest, opt-out | ✅ M7b | AC-NTF-02 `test_ac_ntf_02_mention_email_and_opt_out`, AC-NTF-03 `test_ac_ntf_03_daily_digest_at_seven_local_time`, unit `test_ac_ntf_03_digest_goes_out_at_seven_in_the_users_time_zone`, templates; E2E opt-out | Profile › Notifications |

Also: authz matrix covers every new route (data-transfer routes are initiator-only, covered by the export
test); `br_manifest`: BR-24 in M7. Seed: SPARK v2.5 has a No-go decision and 15 days of snapshots;
`tcms seed --profile large` and `tcms seed-timing` (performance.md). Large seed is 2× year one (L43).

### M7–M9 — status

| Milestone | Epics | Status | Notes |
| --- | --- | --- | --- |
| M3 Plans & cycles | E07, E08 | ✅ done (merged, PR #9) | See the M3 section above |
| M4 Execution runner | E09 | ✅ done (merged, PR #10) | See the M4 section above |
| M5 Bug links | E10 | ✅ done (merged, PR #12) | See the M5 section above (ADR-023) |
| M6 Requirements, RTM, search | E11, E12 | ✅ done (merged, PR #13) | See the M6 section above (ADR-024) |
| M7 Reporting & readiness | E13, E16 | ✅ M7a merged (PR #14); M7b done (awaiting review) | See the M7a section above (ADR-025) |
| M8 Import/export, admin UI, hardening | E14, E15 (UI), E17 | ⬜ not started | US-150…154, US-162…166, US-180…184 |
| M9 Pilot & go-live | — | ⬜ not started | US-185 |
