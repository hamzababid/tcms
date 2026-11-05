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

### M3–M9 — not started

Confirmed from code: `planning`, `execution`, `defects`, `requirements`, `reporting` contain only
`models.py` (M0 baseline ORM); no service/rules/router/screens. Frontend has only auth, profile,
projects, admin and testdesign features.

| Milestone | Epics | Status | Notes |
| --- | --- | --- | --- |
| M3 Plans & cycles | E07, E08 | ⬜ not started | Next milestone. US-070…074, US-080…087; TCMS-025b, 050…060; BR-03/04/05/11/12/31 |
| M4 Execution runner | E09 | ⬜ not started | US-090…100; roll-up (BR-06…10/30/32); confirm K2 before starting |
| M5 Defects | E10 | ⬜ not started | US-110…117; BR-19…22; AC-DEF-01 ordering (K17j) |
| M6 Requirements, RTM, search | E11, E12 | ⬜ not started | US-120…123, US-130…133; BR-23 |
| M7 Reporting & readiness | E13, E16 | ⬜ not started | US-140…146, US-170…171; BR-24; `reporting/metrics.py` not yet created |
| M8 Import/export, admin UI, hardening | E14, E15 (UI), E17 | ⬜ not started | US-150…154, US-162…166, US-180…184 |
| M9 Pilot & go-live | — | ⬜ not started | US-185 |
