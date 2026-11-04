# 02 — Functional Specification

| Field | Value |
| --- | --- |
| Version | 1.0 · 2026-11-03 |
| Depends on | [01 PRD](01-PRD.md) (FR, BR, NFR IDs) |
| Used by | [05 Database](05-Database-Design.md), [06 API](06-API-Specification.md), [07 UI/UX](07-UI-UX-Specification.md), [08 QA](08-QA-Strategy.md), [10 Backlog](10-Backlog.md) |

This document defines exact behaviour: fields, validation, business logic, permissions, errors, edge cases and acceptance criteria. Where it conflicts with another document, **this document wins for behaviour** and [05 Database](05-Database-Design.md) wins for storage details; raise the conflict in the decision log.

Acceptance criteria are written as `AC-<module>-<n>` in Given/When/Then form and are the basis for tests in [08 QA Strategy](08-QA-Strategy.md).

---

## 1. Conventions

- **MVP** marks behaviour delivered in the MVP; **P2/P3** marks later phases. Unmarked = MVP.
- "User" means an authenticated user acting within one organization.
- `code` style names are API/DB identifiers (enum values, field names).
- All limits in this document are defaults, configurable only where stated.

## 2. Global behaviour

### 2.1 Identifiers

| Kind | Format | Rule |
| --- | --- | --- |
| Internal ID | UUIDv7 | Primary key of every table; used in API paths. |
| Project key | `^[A-Z][A-Z0-9]{1,9}$` | Unique per organization; immutable (BR-27). |
| Human key | `<PROJECT>-<PREFIX>-<n>` | Sequential per project and entity; never reused (BR-16). |

Human key prefixes: test case `TC`, test plan `PL`, cycle `CY`, defect `D`, requirement `R`. Example: `SPARK-TC-1042`, `SPARK-D-87`.

Runs have no human key; they are shown as `<cycle key> / <case key>` (e.g. `SPARK-CY-12 / SPARK-TC-1042`).

### 2.2 Time

- Stored in UTC (`timestamptz`); displayed in the user's time zone (profile setting, default browser zone).
- Dates without time (release dates, cycle dates) are calendar dates (`date`) with no zone.

### 2.3 Rich text

- Long text fields accept **Markdown** (CommonMark + tables + task lists). Raw HTML is not allowed; rendered output is sanitized.
- Images pasted into a Markdown field are uploaded as attachments of the owning record and referenced by attachment ID (`![](attachment:<uuid>)`).
- Max length per Markdown field: 20,000 characters unless stated.

### 2.4 Optimistic concurrency (BR-25)

- Every mutable record has `row_version` (integer). Read responses include it; update requests must send it (`If-Match` header or `row_version` body field).
- Mismatch → `409 conflict` with the current record. The UI shows "This item was changed by <user> at <time>" with options **Reload** (discard mine) or **Compare** (side-by-side, then re-apply).
- Step results in a draft attempt are saved individually and are last-write-wins per step (only the executor can edit; see BR-06), so they do not use `row_version`.

### 2.5 Archive vs delete

- Most entities are **archived** (`archived_at` set), not deleted. Archived items are hidden from default lists and pickers, remain readable, and appear in history and reports.
- Hard delete exists only where stated (cases never run, empty folders, draft attempts, unused tags, own comments within 15 minutes).

### 2.6 Lists

All list screens and endpoints support:

- Pagination: `page` (1-based), `page_size` (default 50, max 200), response includes `total`.
- Sorting: `sort=field` or `sort=-field`; up to 3 fields comma-separated; sortable fields listed per entity.
- Filtering: field filters as query parameters (see [06 API §2.6](06-API-Specification.md)); free text `q`.
- Column selection and saved views (§12).
- Bulk selection: select page, or "select all N matching" (server-side, max 5,000 per bulk action).

### 2.7 Notifications

In-app notifications (bell) are MVP; email is MVP for invitations, password reset, and assignment digests (opt-out per user).

| Event | Recipients | Channel |
| --- | --- | --- |
| Runs assigned to me | Assignee | In-app; daily email digest (opt-out) |
| Case submitted for review | Reviewer (or all users with `testcase.approve` if none) | In-app |
| Case approved / returned | Author | In-app |
| Defect assigned to me | Assignee | In-app + email (opt-out) |
| Defect transitioned | Reporter, assignee, watchers | In-app |
| Defect Ready for Retest | Reporter and executors of linked runs | In-app + email (opt-out) |
| Mentioned in a comment (`@user`) | Mentioned user | In-app + email (opt-out) |
| Import/export finished | Initiator | In-app |

## 3. Identity and access (AUTH)

### 3.1 Permission catalog

Permissions are code-defined constants (seeded; not user-creatable). Roles bundle them.

| Permission | Scope | Allows |
| --- | --- | --- |
| `org.manage` | Org | Edit organization settings, security policy |
| `org.users.manage` | Org | Invite, deactivate, reactivate users; reset MFA; revoke sessions |
| `org.roles.manage` | Org | (P2) create/edit custom roles |
| `org.integrations.manage` | Org | (P2) manage integration connections |
| `org.audit.view` | Org | Organization audit log, access review export |
| `org.reports.view` | Org | Organization dashboard across all projects |
| `project.create` | Org | Create projects |
| `project.view` | Project | Read everything in the project |
| `project.configure` | Project | Edit project settings, environments, releases, archive project |
| `project.members.manage` | Project | Add/remove members, change project roles |
| `project.audit.view` | Project | Project audit log |
| `folder.manage` | Project | Create, rename, move, archive, delete folders |
| `testcase.create` | Project | Create and duplicate cases, import cases |
| `testcase.edit` | Project | Edit cases (new versions, metadata), bulk edit, tags |
| `testcase.approve` | Project | Approve or return versions |
| `testcase.archive` | Project | Archive, restore, deprecate |
| `testcase.delete` | Project | Hard delete never-run cases |
| `plan.manage` | Project | Create/edit/clone/archive plans |
| `cycle.manage` | Project | Create/edit/close cycles, add/remove runs, assign, update/replace runs, edit others' drafts |
| `cycle.reopen` | Project | Reopen closed cycles |
| `run.execute` | Project | Start, record, finalize attempts; claim pool runs |
| `defect.create` | Project | Create defects, link defects to results |
| `defect.edit` | Project | Edit defect fields, assign |
| `defect.transition.any` | Project | Any allowed transition |
| `defect.transition.dev` | Project | Developer transitions (§8.2) |
| `defect.transition.verify` | Project | Verifier transitions (§8.2) |
| `requirement.manage` | Project | Create/edit/archive/import requirements |
| `requirement.link` | Project | Link/unlink requirements and cases |
| `release.manage` | Project | Create/edit releases, record go/no-go |
| `data.export` | Project | Export lists and reports |
| `comment.create` | Project | Comment on any readable record |

### 3.2 Default roles (MVP, read-only)

✓ = granted. Org Admin has every permission at org scope and is treated as holding every project permission in every project of the organization (the first access per session to a project they are not a member of is audited as `project.admin_accessed`).

| Permission | QA Manager | QA Lead | QA Engineer | Developer | PM/BA | Viewer |
| --- | --- | --- | --- | --- | --- | --- |
| project.view | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| project.configure | ✓ | | | | | |
| project.members.manage | ✓ | | | | | |
| project.audit.view | ✓ | | | | | |
| folder.manage | ✓ | ✓ | | | | |
| testcase.create | ✓ | ✓ | ✓ | | | |
| testcase.edit | ✓ | ✓ | ✓ | | | |
| testcase.approve | ✓ | ✓ | | | | |
| testcase.archive | ✓ | ✓ | | | | |
| testcase.delete | ✓ | | | | | |
| plan.manage | ✓ | ✓ | | | | |
| cycle.manage | ✓ | ✓ | | | | |
| cycle.reopen | ✓ | | | | | |
| run.execute | ✓ | ✓ | ✓ | | | |
| defect.create | ✓ | ✓ | ✓ | ✓ | | |
| defect.edit | ✓ | ✓ | ✓ | ✓ | | |
| defect.transition.any | ✓ | ✓ | | | | |
| defect.transition.dev | | | | ✓ | | |
| defect.transition.verify | | | ✓ | | | |
| requirement.manage | ✓ | | | | ✓ | |
| requirement.link | ✓ | ✓ | ✓ | | ✓ | |
| release.manage | ✓ | | | | | |
| data.export | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| comment.create | ✓ | ✓ | ✓ | ✓ | ✓ | |

`project.create` (org scope) is granted to Org Admin and, via an organization setting "QA Managers may create projects" (default on), to any user who holds QA Manager in at least one project.

Organization-level membership role: every user is an org **Member**; some are **Org Admin**. An org Member with no project memberships sees only the empty project list and their profile.

### 3.3 Sign-in flow

1. User submits email + password.
2. If credentials invalid → generic error "Email or password is incorrect" (no user enumeration); failed attempt recorded.
3. If account locked → "Too many attempts. Try again in N minutes." (Still generic about whether the email exists: locked message only shown after the password check would have passed or when the account exists; implement as: lock state checked after password verification, generic error otherwise.)
4. If user deactivated → generic error.
5. If MFA enrolled → MFA challenge (TOTP 6 digits or recovery code). 5 failed MFA attempts invalidates the pending login.
6. If MFA required (Org Admin, or org policy) but not enrolled → forced enrolment screen before any other page.
7. Session created; CSRF token issued; redirect to last project or My Work.

**Validation and policy**

| Item | Rule |
| --- | --- |
| Email | RFC 5322 simplified, max 254, stored lower-case, unique per deployment |
| Password | 12–128 chars; not in common-password list; not equal to email; no composition rules |
| Lockout | 10 failures in 15 min → locked 15 min (NFR-SEC-04) |
| Rate limit | 20 auth requests/min per IP |
| TOTP | RFC 6238, SHA-1, 30 s, 6 digits, ±1 step tolerance, replay of the same code rejected |
| Recovery codes | 10 codes, 10 chars, single use, stored hashed |
| Reset link | Single use, 60 min expiry, invalidates other reset links and all sessions on use |
| Password change | Requires the current password; signs out the user's other sessions and emails a notice |
| Invitation | Single use, 7 days, carries org and optional project + role |

**AC**

- AC-AUTH-01: Given a valid user without MFA and no MFA policy, when they sign in with correct credentials, then a session is created and the response sets an HttpOnly Secure cookie.
- AC-AUTH-02: Given an unknown email, when sign-in is attempted, then the response is identical (status, body, timing within 50 ms average) to a wrong password.
- AC-AUTH-03: Given 10 failed attempts within 15 minutes, when the 11th attempt uses the correct password, then sign-in is refused and an audit event `auth.locked` exists.
- AC-AUTH-04: Given an Org Admin without MFA, when they sign in, then every API call returns `403 mfa_enrollment_required` except `GET /auth/me`, `POST /auth/logout`, `POST /auth/mfa/setup` and `POST /auth/mfa/enable`.
- AC-AUTH-05: Given a used recovery code, when it is used again, then it is rejected.
- AC-AUTH-06: Given an idle session older than the idle timeout, when any request is made, then `401 session_expired`.
- AC-AUTH-07: Given a password reset, when completed, then all of the user's sessions and other reset links are revoked; API tokens stay valid unless the user also chooses "revoke API tokens" (`revoke_api_tokens: true`).

### 3.4 API tokens

- Created by a user for themselves; name, expiry (max 365 days, default 90), scope: `read` or `read_write`, optional project restriction (P2: `automation:submit`).
- Token acts with the creating user's permissions intersected with its scope. Deactivating the user disables tokens.
- Shown once (`tcms_` + 40 random chars); stored as SHA-256 hash; last-used time tracked.

### 3.5 User administration

| Action | Permission | Rules |
| --- | --- | --- |
| Invite user | `org.users.manage` (or `project.members.manage` for existing users into a project) | Email must not be an active user; invitation can pre-assign a project role |
| Deactivate user | `org.users.manage` | Cannot deactivate self or the last Org Admin; sessions and tokens revoked; assignments stay (shown with "deactivated" badge) |
| Reset user's MFA | `org.users.manage` | Requires reason; user must re-enrol on next sign-in |
| Change org admin flag | `org.users.manage` | Cannot remove last Org Admin |
| Revoke sessions | `org.users.manage` | Immediate |

Edge cases: a deactivated user's name still renders in history; their open assigned runs appear in the cycle's "Unassigned/inactive" filter so leads can reassign.

## 4. Workspace (WS)

### 4.1 Organization

Fields: `name` (1–100), `slug` (immutable), security policy (`mfa_required_for_all` bool, `session_idle_minutes` 15–480, `session_absolute_hours` 1–24), `qa_managers_can_create_projects` bool, `default_attachment_max_mb` (1–100, default 25), `audit_retention_years` (1–10, default 3).

### 4.2 Project

| Field | Type | Rules |
| --- | --- | --- |
| name | text 1–100 | Unique (case-insensitive) in org among non-archived |
| key | text | BR-27 |
| description | Markdown | Optional |
| status | `active`/`archived` | Archived projects are read-only; reports still work |
| settings.approval_required | bool, default false | BR-17 |
| settings.allow_self_approval | bool, default false | BR-18 |
| settings.only_assignee_executes | bool, default false | BR-32 |
| settings.report_module_depth | int 1–5, default 1 | Folder depth used as "module" in reports |
| settings.attachment_max_mb | int 1…org `default_attachment_max_mb` | The org value is both the default for new projects and the cap; platform cap 100 MB |
| settings.require_defect_for_failure | bool, default false | If true, finalizing a Failed attempt requires a linked defect |

Creating a project: creator becomes QA Manager; default environments `QA` and `Staging` created; root folder is implicit (folders with `parent_id = null` are top-level).

Archiving a project: requires typing the project key; all cycles must be Closed (or the dialog offers to close them).

### 4.3 Environments

Fields: `name` (1–50, unique in project), `description`, `archived_at`. Used by plans (list), cycles (exactly one in MVP), results (copied from cycle), defects (optional). Archived environments cannot be chosen for new cycles.

### 4.4 Releases

| Field | Rules |
| --- | --- |
| name | 1–50, unique in project, e.g. `SPARK v2.5` |
| description | Markdown |
| start_date, target_date | Optional; target ≥ start |
| status | `planned` → `active` → `released`; any → `archived`; `released` → `active` allowed (hotfix) |
| released_at | Set when status becomes `released` |
| decision | Go/no-go record (§11.4) |

**AC**

- AC-WS-01: Given project key `SPARK` exists in the org, when another project is created with key `spark`, then it fails with `409 project_key_taken` (keys are upper-cased before comparison).
- AC-WS-02: Given an archived project, when any write endpoint is called, then `409 project_archived`.
- AC-WS-03: Given an environment used by an active cycle, when it is archived, then the cycle keeps working and the environment is not selectable for new cycles.

## 5. Test repository and test cases (TD)

### 5.1 Folders

| Field | Rules |
| --- | --- |
| name | 1–120 chars, trimmed, no `/`, unique among siblings (case-insensitive) |
| parent_id | Null = top level; depth ≤ 10 |
| position | Integer order among siblings |
| description | Optional Markdown |
| archived_at | Archived folder hides its subtree from the default tree; cases inside remain usable unless archived themselves |

Operations: create, rename, move (to another parent; cannot move into own descendant; depth check on whole subtree), reorder (drag), archive/restore (subtree), delete (BR-15).

The tree shows per-folder counts of non-archived cases including descendants. Counts may be up to 60 s stale (cached) for trees > 500 folders.

**AC**

- AC-TD-01: Given folder A with child B, when A is moved under B, then `422 folder_cycle`.
- AC-TD-02: Given a move that would make depth 11, then `422 folder_too_deep`.
- AC-TD-03: Given a folder containing one archived case, when delete is requested, then `409 folder_not_empty`.

### 5.2 Test case fields

Content fields (versioned, BR-01) are marked **V**. Metadata fields are not versioned but audited.

| Field | V | Type | Required | Rules |
| --- | --- | --- | --- | --- |
| key | | text | auto | BR-16 |
| title | V | text 3–255 | yes | Trimmed; duplicates allowed (warning shown when an identical title exists in the same folder) |
| description | V | Markdown | no | Purpose/scope |
| format | V | `steps` / `text` (P2 `exploratory`, `data_validation`; P3 `bdd`) | yes | Changing format creates a new version; step data is discarded when switching to `text` (confirmation) |
| preconditions | V | Markdown | no | |
| test_data | V | Markdown | no | |
| steps | V | list | `steps` format: ≥ 1 | Each: `action` (Markdown, required, ≤ 5,000), `expected_result` (Markdown, optional, ≤ 5,000), `data` (Markdown, optional, ≤ 2,000). Max 100 steps |
| text_body | V | Markdown | `text` format: yes | Free-form procedure |
| expected_result | V | Markdown | no | Overall expected result |
| postconditions | V | Markdown | no | |
| folder_id | | ref | yes | |
| type | | enum | yes, default `functional` | `functional`, `integration`, `end_to_end`, `api`, `ui`, `data_validation`, `performance`, `security`, `compatibility`, `usability` |
| design_technique | | enum | no | `positive`, `negative`, `boundary_value`, `equivalence_partitioning`, `error_guessing` |
| priority | | enum | yes, default `medium` | `critical`, `high`, `medium`, `low` |
| tags | | list | no | Max 20 per case; tag names 1–40 chars `[a-z0-9-_.]`; system tags `smoke`, `sanity`, `regression` always exist |
| owner_id | | user | yes, default creator | Must be a project member |
| reviewer_id | | user | no | Must hold `testcase.approve` |
| automation_status | | enum | yes, default `manual` | `manual`, `automated`, `to_be_automated`, `not_automatable` |
| automation_keys | | list of text | no | Each 1–500 chars, unique per project (P2 used for mapping; editable in MVP) |
| estimated_minutes | | int 0–1440 | no | Used for cycle effort estimate |
| status | | enum | system | `draft`, `in_review`, `approved`, `deprecated`, `archived` (§5.4) |
| created_by/at, updated_by/at | | | system | |
| latest_version / approved_version | | int | system | |

Brief alignment: the brief's single "Test Classification" list mixed three concepts. They are split into `type` (what is tested), `design_technique` (how cases were derived) and system tags (`smoke`, `sanity`, `regression` = which suites a case belongs to). "Module/Feature" is the folder (reports group by folder at `report_module_depth`). Test-case "Severity" is dropped; priority covers it and severity lives on defects. See ADR-012.

"Execution environment" on the case is not a field; environments belong to cycles. A case may state environment constraints in `preconditions`.

### 5.3 Versioning (BR-01, BR-02, BR-05)

- Saving content compares the submitted content with the latest version (normalized: trimmed, line endings `\n`). If identical, no version is created (`200`, `version_created: false`).
- A new version records: `version_no`, all content fields, steps (each with a stable `step_id` per version), `change_note` (optional, ≤ 500), `created_by/at`, `content_hash`.
- The case's denormalized `title` follows the latest version.
- **Compare**: any two versions side by side; per field diff; steps aligned by position with added/removed/changed markers.
- **Restore** version N: creates version M+1 with N's content and change note "Restored from v N".
- Attachments: case-level attachments are linked to the case, not a version (shown in all versions with "added at" time). Step attachments belong to the step of a specific version and are carried forward (re-linked) to the same-position step when a new version is created unless the step was deleted.

**AC**

- AC-TD-10: Given a case at version 3, when only its priority changes, then no version 4 exists and an audit event records `priority` old/new.
- AC-TD-11: Given a case at version 3, when its step 2 expected result changes, then version 4 exists, version 3 is unchanged, and runs pinned to version 3 still show the old text.
- AC-TD-12: Given versions 2 and 5, when compared, then changed fields are highlighted and unchanged steps are collapsed.
- AC-TD-13: Given identical content is saved, then no new version is created.

### 5.4 Status and review workflow

**Approval disabled (default):**

- Every saved version is auto-approved: `approval_mode = auto`, case `status = approved`, `approved_version = latest`.
- Status transitions available: `approved → deprecated → approved`, any → `archived`, `archived → approved` (restore).

**Approval enabled (`settings.approval_required = true`):**

```
            save new version
 approved ───────────────────► draft ──submit──► in_review ──approve──► approved
    ▲                            ▲                   │
    │                            └──── return ───────┘ (comment required)
    └── first approval of a new case: draft → in_review → approved
```

- A new case starts `draft` (version 1, no approved version).
- Saving a new version of an approved case sets `status = draft`; `approved_version` keeps pointing to the last approved version (BR-17).
- `submit` (author or anyone with `testcase.edit`): `draft → in_review`; optional reviewer assignment.
- `approve` (`testcase.approve`; not the version's author unless `allow_self_approval`) approves the **latest** version: `approved_version = latest`, `status = approved`.
- `return` (`testcase.approve`): `in_review → draft`; comment required.
- Editing while `in_review` saves a new version and keeps `in_review` (reviewer sees the newest version).
- `deprecate` (`testcase.archive`): `approved → deprecated`. Deprecated cases remain in existing plans/cycles with a warning badge; cannot be added to new cycles (BR-13). `restore` → previous status.
- `archive` (`testcase.archive`): any → `archived`. Archived cases are hidden, cannot be added to plans or cycles; existing plan membership stays but plan shows "archived" and cycle creation skips them with a warning.
- Turning approval **on** for a project with existing cases: all cases keep `approved` with their latest version as approved version (grandfathered); audit records the setting change.
- Turning approval **off**: cases in `draft`/`in_review` are auto-approved at their latest version.

**AC**

- AC-TD-20: Given approval enabled and case approved at v2, when v3 is saved, then status = draft, approved_version = 2, and a new cycle pins v2.
- AC-TD-21: Given approval enabled and self-approval disallowed, when the author of v3 approves it, then `403 self_approval_not_allowed`.
- AC-TD-22: Given a returned case, then the return comment is visible on the case and the author receives a notification.

### 5.5 Other case operations

| Operation | Rules |
| --- | --- |
| Duplicate | New key, version 1 = copy of latest version content, same metadata (status per approval mode), attachments copied (new objects), link `duplicated_from`. Title prefixed "Copy of " unless target folder differs. |
| Bulk edit | Actions: move to folder, add tags, remove tags, set priority, set type, set owner, set reviewer, set automation status, deprecate, archive, restore, export. Max 5,000 per action; runs in background if > 200; each case gets its own audit event with a shared `bulk_operation_id`. |
| Hard delete | BR-14. Confirmation requires typing the key. |
| Related cases | Undirected link `related` or directed `duplicated_from`; max 50 per case. |
| Requirement links | §10.2 |
| History tab | Versions, audit events, and executions (every run: cycle, version, latest status, executed by/at). |
| Move | Changing folder keeps key; audit event. |

### 5.6 Phase 2/3 formats (summary; full spec at phase start)

- **Shared steps (P2, FR-TD-015):** project-level step blocks with their own versions. A case step can be a reference `{shared_step_id, shared_step_version}`. When a block gets a new version, cases using it show "update available"; adopting creates a new case version. Execution expands the block into its steps.
- **Parameters (P2, FR-TD-016):** a case defines named parameters and a dataset table; a cycle can create one run per dataset row (run label shows the row values); steps substitute `{{name}}`.
- **Exploratory (P2, FR-TD-017):** charter (mission, areas, time box); execution is a session with timestamped notes (note types: bug, issue, question, observation) and a session outcome.
- **Data validation (P2, FR-TD-018):** a table of checks `{name, input/query, rule, expected, tolerance}`; execution records actual value and pass/fail per check, rolled up like steps.
- **BDD (P3):** Gherkin text, scenarios executed like steps.

## 6. Test plans (PLN)

### 6.1 Fields

| Field | Type | Rules |
| --- | --- | --- |
| key | `SPARK-PL-n` | auto |
| name | 3–150 | required |
| type | enum | `functional`, `integration`, `regression`, `release_validation`, `uat`, `smoke`, `performance`, `security` |
| release_id | ref | optional |
| status | enum | `draft`, `active`, `completed`, `archived` |
| objectives | Markdown | |
| scope_in, scope_out | Markdown | in-scope / out-of-scope features |
| environment_ids | list | environments the plan targets |
| entry_criteria | Markdown | |
| exit_criteria | list of readiness rules (§11.4) + Markdown notes | |
| risks | list of `{description, impact: low/medium/high, mitigation}` | max 50 |
| acceptance_criteria | Markdown | |
| start_date, end_date | date | end ≥ start |
| owner_id | user | default creator |
| member_ids | users | QA resources assigned to the plan (informational + default assignee pool) |
| cases | list of case refs | §6.2 |
| requirements | list of requirement refs | |

### 6.2 Case selection

- Add by: individual pick, whole folder (with/without subfolders), tag, or saved filter. Selection is stored as **explicit case IDs** (snapshot), not as a rule. The add dialog shows how many cases each rule adds and how many are excluded (archived/deprecated/unapproved).
- Remove cases freely; removal does not affect existing cycles.
- Plan shows per case: latest result in each linked cycle.

### 6.3 Cycles from a plan

- "Create cycle" prefills name `<plan name> – Cycle <n>`, release, environment (first plan environment), dates, cases (all plan cases or a subset filtered by tag/folder/priority).
- A plan can have any number of cycles (e.g., one per environment or per regression round) — FR-PLN-004.
- "Sync from plan" on a cycle: adds plan cases not yet in the cycle (BR-31).
- Clone plan: copies everything except cycles; name "Copy of …"; status draft.

**AC**

- AC-PLN-01: Given a plan with 200 cases, 3 archived and 2 deprecated, when a cycle is created from it, then 195 runs are created and the response lists the 5 skipped cases with reasons.
- AC-PLN-02: Given a cycle created from a plan, when 10 cases are added to the plan, then the cycle is unchanged until "Sync from plan" is run, which adds 10 runs.

## 7. Execution (EXE)

### 7.1 Cycles

| Field | Rules |
| --- | --- |
| key | `SPARK-CY-n` |
| name | 3–150, required |
| release_id | optional |
| plan_id | optional (set when created from plan) |
| environment_id | required, active environment |
| build | text ≤ 100, optional (build/version under test; default for results) |
| start_date, due_date | optional; due ≥ start |
| description | Markdown |
| status | `planned` → `active` → `closed`; `closed` → `active` via reopen (BR-11) |
| owner_id | default creator |

Runs: one per case (BR-12), ordered by `position` (default: folder tree order, then case key). Lead can reorder by drag or "sort by folder/priority".

**Cycle actions**

| Action | Permission | Rules |
| --- | --- | --- |
| Create | `cycle.manage` | Pins versions per BR-03; > 500 runs created in background (progress shown) |
| Add cases | `cycle.manage` | Not in closed cycle; duplicates skipped (BR-12) |
| Remove runs | `cycle.manage` | Only runs with status `not_run` and no attempts; otherwise `409 run_has_results` |
| Assign / unassign | `cycle.manage` | Bulk; assignee must be a project member with `run.execute` |
| Claim | `run.execute` | Unassigned run → assigned to self |
| Start | `cycle.manage` | `planned → active` (also automatic, BR-30) |
| Close | `cycle.manage` | Draft attempts must be finalized or discarded first (dialog lists them); not-run runs remain not run; `closed_at`, `closed_by` set |
| Reopen | `cycle.reopen` | Reason required; status `active` |
| Clone | `cycle.manage` | New cycle with same cases at **current** eligible versions, no results; option "only failed/blocked/not run from source" for re-test rounds |
| Archive | `cycle.manage` | Closed cycles only; hidden from default lists; still in reports |

### 7.2 Runs

Fields: `cycle_id`, `test_case_id`, `test_case_version_id` (pinned), `assignee_id`, `status` (derived, BR-08), `needs_retest` (BR-21), `superseded_by_run_id`, `position`, `latest_result_id`.

**Version actions**

- Banner on the run when a newer eligible version exists: "v5 available (you are on v3) — view changes".
- **Update to latest** (`cycle.manage`, or the assignee with `run.execute`): allowed only when the run has no attempts (BR-04). Bulk version: "Update all not-run runs in this cycle".
- **Replace run** (`cycle.manage`): run has finalized attempts and is not superseded; creates a new run (same position, same assignee) at the latest eligible version; old run `superseded_by_run_id = new`. Superseded runs appear only with filter "show superseded" (BR-05).

### 7.3 Result attempts

An attempt (`test_results` row) records one execution of a run.

| Field | Rules |
| --- | --- |
| attempt_no | 1..n per run |
| state | `draft` or `final` |
| status | null while draft; on finalize one of `passed`, `failed`, `blocked`, `skipped`, `not_applicable` |
| executed_by | user who started it |
| started_at, finished_at | system |
| duration_seconds | system (finished − started, minus nothing; editable before finalize, 0–86,400) |
| build | defaults from cycle |
| environment_id | copied from cycle |
| comment | Markdown, optional; required if status ∈ {blocked, skipped, not_applicable} (as `reason`) |
| reason | text ≤ 1,000; required for run-level blocked/skipped/not_applicable |
| corrects_result_id | when this attempt corrects an earlier finalized one |
| source | `manual` (P2: `automation`) |
| step results | one per step of the pinned version (`steps` format) |

Step result fields: `status` (`not_run`, `passed`, `failed`, `blocked`, `skipped`), `actual_result` (Markdown, required when `failed`; optional otherwise), `comment`, attachments.

**Lifecycle**

1. **Start** (`run.execute`; cycle not closed; BR-32; no other draft on run — BR-07): creates draft attempt with all step results `not_run`. If the cycle is `planned` it becomes `active` (BR-30). If the run already has a draft by another user → `409 draft_exists` with that user's name; a user with `cycle.manage` may take over (draft's `executed_by` changes; audited).
2. **Record**: each step change is saved immediately (PATCH). Allowed only by the draft's executor or `cycle.manage`.
3. **Finalize**: server computes status by BR-09:
   - Any `failed` → `failed`.
   - Else any `blocked` → `blocked`.
   - Else all steps ∈ {passed, skipped} and ≥ 1 passed → `passed` (`skipped_steps` count stored and shown as "Passed · N skipped").
   - Else (some steps `not_run`, or all skipped): request rejected with `422 incomplete_attempt` unless the request sets an explicit run-level outcome `blocked`, `skipped` or `not_applicable` with `reason`. An explicit `blocked` is also allowed when steps are partly passed (e.g., environment went down mid-run).
   - Explicit outcome cannot contradict steps: explicit `passed` is never accepted; explicit outcome when a step failed → `failed` wins and the request is rejected with `422 outcome_conflicts_with_steps`.
   - `text` format: tester chooses status; `failed` requires comment.
   - If `require_defect_for_failure` and status `failed` and no defect linked to the attempt → `422 defect_required`.
4. On finalize: attempt becomes immutable; run `status` and `latest_result_id` updated; `needs_retest` cleared; audit event `result.finalized`.
5. **Discard draft**: executor or `cycle.manage`; deletes the draft and its step results (audited with a summary of what was recorded). Attachments uploaded to the draft are deleted.

**Retest (FR-EXE-009):** "Retest" on a run with a finalized attempt starts a new attempt (attempt_no + 1). Previous attempts remain visible in the run's history.

**Correction (FR-EXE-010):** "Correct result" on a finalized attempt starts a new attempt with `corrects_result_id`; finalize requires a `reason`. The corrected attempt is shown struck through with a link. Metrics always use the latest finalized attempt, so a correction replaces it in figures. Only `cycle.manage` or the original executor (within the same cycle while not closed) may correct.

**Status precedence summary (BR-08, BR-09)** — see also [08 QA §6](08-QA-Strategy.md) for the test matrix.

| Step statuses on finalize | Explicit outcome sent | Result |
| --- | --- | --- |
| All passed | none | passed |
| Passed + skipped (≥ 1 passed) | none | passed (skipped flagged) |
| Any failed | none / any | failed (explicit non-failed → 422) |
| No failed, any blocked | none | blocked |
| All skipped | none | 422 incomplete_attempt |
| All skipped | skipped / not_applicable + reason | skipped / not_applicable |
| Some not_run, no failed/blocked | none | 422 incomplete_attempt |
| Some not_run, no failed | blocked + reason | blocked |
| Some not_run | not_applicable + reason | not_applicable |

**AC**

- AC-EXE-01: Given a draft with steps [passed, failed, not_run], when finalized, then status = failed.
- AC-EXE-02: Given a draft with steps [passed, skipped, passed], when finalized, then status = passed and skipped_steps = 1.
- AC-EXE-03: Given a draft with steps [passed, not_run], when finalized without outcome, then `422 incomplete_attempt`.
- AC-EXE-04: Given a finalized attempt, when any update to it or its step results is attempted (API or SQL as app user), then it is rejected.
- AC-EXE-05: Given a run with a draft by user A, when user B (no cycle.manage) starts an attempt, then `409 draft_exists`.
- AC-EXE-06: Given a closed cycle, when an attempt is started, then `409 cycle_closed`.
- AC-EXE-07: Given a run with a failed final attempt, when a retest passes, then run status = passed, attempt history shows both, and metrics count the run as passed.
- AC-EXE-08: Given a case edited to v4 while a run is pinned to v3 with a result, then the run still displays v3 steps, and "Update to latest" is disabled with tooltip "Run has results — use Replace run".
- AC-EXE-09: Given 50 testers saving step results concurrently on different runs, then no update is lost and p95 save latency < 200 ms.

### 7.4 Execution screen behaviour (summary; layout in [07 UI §5.9](07-UI-UX-Specification.md))

- Queue: the cycle's runs filtered (default: assigned to me, not finalized), in position order. "Next" moves to the next run in the queue without leaving the page.
- Keyboard: `P` pass, `F` fail, `B` blocked, `S` skip, `↓`/`J` next step, `↑`/`K` previous step, `Space` start attempt, `A` attach, `Ctrl+Enter` finish run, `Shift+N` next run, `D` raise defect from current step, `?` help.
- Selecting **Fail** focuses the actual-result field (required before leaving the step).
- "Pass all remaining" button (sets all `not_run` steps to passed; confirmation when > 10 steps).
- Paste image into actual result / comment → uploaded as step attachment.
- Offline tolerance: if a save fails, the step shows "not saved" and retries every 5 s; finishing is disabled until all saves succeed.

### 7.5 My Work

Lists runs assigned to the user in active and planned cycles across projects, grouped by cycle, with counts by status, due dates, and `needs_retest` flags. Also: defects assigned to me, cases awaiting my review.

## 8. Defects (DEF)

### 8.1 Fields

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| key | `SPARK-D-n` | auto | |
| title | 5–255 | yes | |
| description | Markdown | no | |
| steps_to_reproduce | Markdown | yes | Prefilled from run (§8.3) |
| expected_result | Markdown | yes | |
| actual_result | Markdown | yes | |
| severity | `critical`/`high`/`medium`/`low` | yes | default `medium` |
| priority | `critical`/`high`/`medium`/`low` | yes | default `medium` |
| status | §8.2 | system | initial `open` |
| environment_id | ref | no | |
| build | text ≤ 100 | no | |
| browser_device | text ≤ 200 | no | |
| folder_id | ref | no | "Module" for reporting; prefilled from case folder |
| found_in_release_id | ref | no | prefilled from cycle |
| fix_version | text ≤ 100 | no | |
| reporter_id | user | system | |
| assignee_id | user | no | project member |
| resolution | enum | on certain transitions | `fixed`, `wont_fix`, `duplicate`, `cannot_reproduce`, `not_a_bug`, `deferred` |
| resolution_note | Markdown | per §8.2 | |
| duplicate_of_id | ref | when duplicate | same project, not itself, not creating a chain loop |
| watchers | users | no | |
| links | results, cases, requirements | | §8.3 |
| retest status | derived | | `not_required`, `pending` (ready_for_retest and linked runs not retested), `passed`, `failed` (latest retest results of linked runs) |

### 8.2 Lifecycle (BR-19)

States: `open`, `triaged`, `assigned`, `in_progress`, `fixed`, `ready_for_retest`, `verified`, `closed`, `reopened`, `rejected`, `duplicate`, `cannot_reproduce`, `deferred`.

**Open set** (counted as open defects): `open`, `triaged`, `assigned`, `in_progress`, `fixed`, `ready_for_retest`, `reopened`. **Deferred** is counted separately. **Resolved set**: `verified`, `closed`, `rejected`, `duplicate`, `cannot_reproduce`.

| From | To | Permission (any of) | Required input |
| --- | --- | --- | --- |
| open | triaged | any | severity, priority confirmed |
| open, triaged | assigned | any | assignee |
| open, triaged, reopened | rejected | any | resolution_note |
| open, triaged, reopened | duplicate | any | duplicate_of_id |
| open, triaged, in_progress | cannot_reproduce | any, dev (from in_progress) | resolution_note |
| open, triaged, assigned, in_progress | deferred | any | resolution_note |
| assigned, reopened | in_progress | any, dev | — |
| in_progress | assigned | any, dev | — (dev handing back) |
| in_progress | fixed | any, dev | resolution `fixed` (default), resolution_note optional, fix_version optional |
| fixed | ready_for_retest | any | — |
| fixed, ready_for_retest | reopened | any, verify | comment |
| ready_for_retest | verified | any, verify | — |
| verified | closed | any, verify | — |
| verified, closed | reopened | any, verify | comment |
| rejected, duplicate, cannot_reproduce | reopened | any | comment |
| rejected, duplicate, cannot_reproduce, deferred | closed | any | — |
| deferred | triaged | any | — |
| reopened | triaged, assigned | any | assignee if assigned |

"any" = `defect.transition.any`; "dev" = `defect.transition.dev` and the user is the assignee; "verify" = `defect.transition.verify`. Org Admins hold all. Every transition records a `defect_status_history` row (from, to, by, at, note) and an audit event. Moving to `assigned` without an assignee is rejected; changing the assignee of an `open`/`triaged` defect moves it to `assigned` automatically.

### 8.3 Defects from execution (BR-20, BR-21)

- "Raise defect" from a step in a draft or finalized attempt opens the defect form prefilled:
  - title: `<case title> – step <n> failed` (editable),
  - steps_to_reproduce: preconditions + steps 1..n (action + data) of the pinned version, numbered,
  - expected_result: step n expected result,
  - actual_result: step n actual result,
  - environment, build, found_in_release, folder (module) from the run,
  - attachments: the step's attachments copied by reference,
  - links: result attempt, run, case, failing step id.
- "Link existing defect" from a step: search by key/title; creates link only.
- A defect can link to many results across cycles and to cases directly (e.g., a defect found outside execution).
- When status → `ready_for_retest`: linked non-superseded runs in non-closed cycles get `needs_retest = true` (BR-21); executors of the linked attempts are notified.
- Retest of a linked run that passes: the runner shows "Defect SPARK-D-87 is Ready for Retest — mark Verified?" (BR-22). Failing retest: "Reopen SPARK-D-87?".

### 8.4 Defect list

Filters: status (set or open/resolved/deferred groups), severity, priority, assignee, reporter, module (folder), release found, environment, created/updated date range, linked cycle, has Jira link (P2), text. Bulk: assign, transition (only transitions valid for all selected and permitted), set priority/severity, add watchers, export.

**AC**

- AC-DEF-01: Given a defect in `open`, when a developer (dev permission only) transitions it to `fixed`, then `403 transition_not_permitted`.
- AC-DEF-02: Given a defect raised from step 3 of a failed attempt, then its steps_to_reproduce contains preconditions and steps 1–3 and it is linked to the attempt, run and case.
- AC-DEF-03: Given a defect linked to two runs in an active cycle, when it moves to ready_for_retest, then both runs show needs_retest.
- AC-DEF-04: Given a duplicate transition without duplicate_of_id, then `422 field_required`.

## 9. Comments, attachments, activity

### 9.1 Comments

- On test cases (optionally anchored to a version), runs/attempts, defects, requirements, plans, cycles.
- Markdown, ≤ 10,000 chars, `@mention` project members.
- Author can edit/delete within 15 minutes; afterwards immutable (edits shown as "edited"; old text in audit).
- Review comments on a case version are shown in the review panel.

### 9.2 Attachments

- Allowed types (by content sniffing): images (png, jpeg, gif, webp), pdf, txt, log, csv, json, xml, har, zip, xlsx, docx, mp4/webm (≤ limit).
- Max size: project setting (default and cap = organization `default_attachment_max_mb`, default 25 MB; platform cap 100 MB). Max 50 attachments per record.
- Filename sanitized; stored under random object key; original name kept for download.
- Previews for images and PDF; others download.
- Deletion: uploader or `cycle.manage`/`testcase.edit`/`defect.edit` on the owning record, unless BR-28 forbids.

### 9.3 Activity feed

Project feed shows recent audit events rendered as sentences ("Sana finalized SPARK-CY-12 / SPARK-TC-1042 as Failed"), filterable by entity type and user.

## 10. Requirements and traceability (REQ)

### 10.1 Requirement fields

| Field | Rules |
| --- | --- |
| key | `SPARK-R-n`; for Jira-mirrored (P2) also `external_key` (e.g. `SPK-431`) |
| title | 3–255 |
| description | Markdown |
| type | `epic`, `feature`, `user_story`, `functional`, `non_functional`, `business` |
| priority | `critical`, `high`, `medium`, `low` |
| acceptance_criteria | Markdown (task-list syntax encouraged; each criterion can be referenced in P2) |
| owner_id | project member |
| status | `draft`, `approved`, `implemented`, `obsolete` |
| target_release_id | optional |
| parent_id | optional; same project; no cycles; depth ≤ 5 |
| source | `internal` (P2: `jira`) — `jira` requirements are read-only except links |
| archived_at | |

### 10.2 Links

- Many-to-many requirement ↔ test case (FR-REQ-002); created from either side; bulk link from case list ("Link selected to requirement…").
- Requirement ↔ defect links are derived (defects linked to the requirement's cases' results) plus optional direct links.
- Links are not versioned; adding/removing is audited.

### 10.3 Release scope for a requirement

A requirement is **in scope for release R** if `target_release_id = R` or it is linked to a test plan whose `release_id = R`.

### 10.4 Traceability matrix (RTM)

Rows: requirements in scope for the selected release (or all non-archived requirements when no release selected), hierarchical by parent. Columns:

| Column | Content |
| --- | --- |
| Requirement | key, title, type, priority |
| Coverage | number of linked active cases |
| Cases | expandable list: case key/title, latest result in release (status badge, cycle, date), link |
| Status in release | §10.5 |
| Defects | open defects linked via results in the release or directly (count by severity, expandable) |

Filters: release, status in release, uncovered only, priority, type, owner. Export CSV/XLSX (one row per requirement–case pair).

### 10.5 Coverage computation (BR-23)

For release R and requirement Q:

- `linked_cases(Q)` = cases linked to Q whose status ≠ `archived`.
- **Covered** ⇔ `|linked_cases(Q)| ≥ 1`.
- For each linked case C: `latest(C, R)` = the latest finalized attempt (by `finished_at`) among non-superseded runs of C in cycles with `release_id = R`, ignoring attempts with status `not_applicable`; null if none.
- **Status in release**:
  1. `not_covered` if not covered;
  2. `failed` if any `latest(C,R).status = failed`;
  3. `blocked` if any is `blocked`;
  4. `not_run` if any `latest(C,R)` is null or `skipped`;
  5. `passed` otherwise (all linked cases passed).
- Without a release filter, the same rules apply across all cycles of the project.

Coverage metrics (per release):

| Metric | Definition |
| --- | --- |
| Total requirements | in-scope, non-archived, status ≠ obsolete |
| Covered | status ≠ not_covered |
| Not covered | status = not_covered |
| Passed / Failed / Blocked / Not run | count by status in release |
| Coverage % | Covered ÷ Total (show both numbers) |
| Verified % | Passed ÷ Total (show both numbers) |

**AC**

- AC-REQ-01: Given requirement Q linked to cases A (latest passed) and B (no result in R), then Q's status in R = not_run.
- AC-REQ-02: Given A passed and B failed, then status = failed.
- AC-REQ-03: Given Q linked only to an archived case, then Q is not_covered.
- AC-REQ-04: Given A failed in cycle 1 and passed in a later retest in cycle 2 of the same release, then A counts as passed.

## 11. Dashboards and reporting (RPT)

### 11.1 Common filters

Release, cycle(s), date range (applies to `finished_at` of attempts or `created_at` of defects), module (folder at configured depth), tester (`executed_by` for results, `assignee` for pending), environment. Dashboards remember the last filter per user (local preference).

### 11.2 Metric definitions (BR-24)

Let **runs in scope** = non-superseded runs in the selected cycles (or all cycles of the selected release). For each run use its current status (BR-08).

| Metric | Formula | Notes |
| --- | --- | --- |
| Total runs | count(runs in scope) | |
| Not applicable | count(status = not_applicable) | Shown, excluded from denominators |
| Applicable runs (A) | Total − Not applicable | |
| Passed (P), Failed (F), Blocked (B), Skipped (S), Not run (NR), In progress (IP) | counts by status | NR includes runs never started |
| Executed (E) | P + F + B | Skipped and in-progress are not executed |
| Execution progress | E ÷ A | Displayed "E of A (x%)"; 0 when A = 0 shown as "—" |
| Pass rate | P ÷ E | Displayed "P of E (x%)"; "—" when E = 0, never 0% or 100% |
| Pass rate of applicable | P ÷ A | Shown in release readiness ("x% of applicable tests have passed") |
| Failure rate | F ÷ E | |
| Blocked rate | B ÷ A | |
| First-time pass rate | runs whose first finalized attempt passed ÷ runs with ≥ 1 finalized attempt (excluding NA) | Advanced (P2) |
| Retest count | finalized attempts with attempt_no > 1 | |
| Open defects | count(defects in open set) | Filtered by found_in_release when a release is selected |
| Critical/high open defects | open defects with severity ∈ {critical, high} | |
| Defect age | now − created_at for open defects; median and max | |
| Requirement coverage | §10.5 | |
| Automation coverage | cases with automation_status = automated ÷ active cases | Repository metric |
| Total test cases | active cases (status ≠ archived) | Repository metrics count cases, not runs |

Charts never show a percentage without its counts in the tooltip or label.

### 11.3 Dashboards

**QA Manager dashboard (project)** — filters §11.1.

| Widget | Content |
| --- | --- |
| Repository | Total active cases, by status, by type; total folders ("suites"); total plans (by status) |
| Active cycles | List: name, release, environment, progress bar (P/F/B/S/NR segments), due date, overdue flag |
| Execution summary | Counts and rates from §11.2 for scope |
| Status breakdown | Stacked bar per cycle |
| Defects | Open by severity; critical/high list; opened vs resolved last 30 days |
| Requirement coverage | Covered/Total, Verified/Total for selected release; top 10 uncovered |
| Regression status | Runs of cases tagged `regression` in scope: progress + pass rate |
| Release readiness | §11.4 |
| Team progress | Per tester: assigned, executed, remaining, failed, blocked |

**QA Engineer dashboard (My Work)** — §7.5 plus: my executed runs today/this week, my failed and blocked runs awaiting retest, defects assigned to or reported by me, upcoming cycles (start date in next 14 days) where I have assignments.

**Project quality dashboard**

| Widget | Content |
| --- | --- |
| Execution trend | Daily executed and pass rate over date range (from `metric_snapshots` + today live) |
| Pass/fail trend | Daily P/F/B counts |
| Defect trend | Opened, resolved, open total per day |
| Defects by severity | Current open by severity |
| Defects by module | Open by folder at module depth |
| Requirement coverage | Per release |
| Automation coverage | Repository automation status distribution |
| Regression status | Per release |
| Release-wise quality | For last 6 releases: pass rate of applicable, open critical/high at release date, defects found, coverage % |

**Organization dashboard:** per project row: active cycles, execution progress, pass rate, open critical/high defects, last activity.

### 11.4 Release readiness (FR-RPT-006)

Readiness rules come from plan exit criteria for plans in the release, plus default rules if none exist. Rule types:

| Rule type | Parameters | Evaluation |
| --- | --- | --- |
| `min_execution_progress` | percent | Execution progress ≥ value |
| `min_pass_rate` | percent | Pass rate (P ÷ E) ≥ value |
| `min_pass_rate_applicable` | percent | P ÷ A ≥ value |
| `max_open_defects` | severity set, count | Open defects with those severities found in release ≤ count |
| `max_blocked` | count | Blocked runs ≤ count |
| `min_requirement_coverage` | percent | Coverage % ≥ value |
| `min_requirements_verified` | percent | Verified % ≥ value |
| `tag_fully_executed` | tag | All runs of cases with that tag executed |

Defaults (when no plan exit criteria): execution progress ≥ 100%, no open critical defects, pass rate of applicable ≥ 95%, requirement coverage ≥ 90%.

Panel shows each rule: met/not met, actual value with counts, threshold. Overall: **Ready** only if all met. The QA Manager (`release.manage`) records a **decision**: `go`, `go_with_risks` (risks text required), `no_go`, comment required; a snapshot of all rule results and metrics is stored with the decision (immutable). Multiple decisions over time allowed; latest shown.

### 11.5 Reports and export (FR-RPT-004/005)

MVP reports (each a filterable table + CSV/XLSX export, `data.export`):

| Report | Rows |
| --- | --- |
| Cycle execution report | One row per run: case key, title, folder, priority, assignee, status, executed by, finished at, version, defects |
| Results history | One row per finalized attempt in range |
| Defect report | One row per defect with all fields |
| Traceability report | One row per requirement–case pair with status in release |
| Tester activity | Per tester per day: executed, passed, failed, blocked |
| Test case inventory | One row per case with metadata and latest result |

Exports ≤ 10,000 rows are synchronous; larger exports run as background jobs (max 500,000 rows) and notify on completion; files kept 7 days.

## 12. Search, filters, saved views (SRCH)

- **Global search** (header, `/` shortcut): scoped to current project by default with "all projects" toggle. Matches: exact key (`SPARK-TC-12`, also `TC-12`, `12` within project), external keys (P2), titles (prefix + trigram fuzzy), folder names, cycle/plan names, requirement and defect titles and descriptions (full text). Results grouped by type, top 5 each, "see all" → filtered list.
- **Filters**: each list defines filterable fields; operators: `is`, `is not`, `in`, `contains`, `before/after/between` (dates), `is empty`. Combined with AND; multi-value fields with OR within a field.
- **Saved views**: name, entity type, filters, columns, sort; visibility `private` or `project` (shared requires `cycle.manage` or `plan.manage` or `project.configure`). Users can set a default view per list.

## 13. Audit and activity (AUD)

### 13.1 What is recorded

Every audit event: `id`, `occurred_at`, `organization_id`, `project_id` (nullable), `actor_type` (`user`, `api_token`, `system`, `integration`), `actor_id`, `action` (e.g. `test_case.version_created`), `entity_type`, `entity_id`, `entity_key`, `changes` (JSON `{field: [old, new]}`), `context` (request ID, IP, user agent, bulk_operation_id, reason), `summary` (rendered sentence).

| Area | Actions (minimum) |
| --- | --- |
| Auth | `auth.login_succeeded`, `auth.login_failed`, `auth.locked`, `auth.logout`, `auth.mfa_enrolled`, `auth.mfa_disabled`, `auth.mfa_reset`, `auth.recovery_codes_regenerated`, `auth.password_changed`, `auth.password_reset_requested`, `auth.password_reset`, `api_token.created`, `api_token.revoked`, `session.revoked`. A failed sign-in for an email with no account writes only a `login_attempts` row (there is no organization to audit in) |
| Users & roles | `user.invited`, `user.activated`, `user.deactivated`, `membership.granted`, `membership.changed`, `membership.revoked`, `org_admin.granted/revoked`, `project.admin_accessed`, `user.reactivated`, `user.updated`, `user.invitation_revoked` |
| Config | `organization.updated`, `project.created/updated/archived/restored`, `release.status_changed`, `project.settings_changed`, `environment.*`, `release.*`, `release.decision_recorded` |
| Test design | `folder.*`, `test_case.created`, `test_case.version_created`, `test_case.updated` (metadata), `test_case.submitted/approved/returned/deprecated/archived/restored/deleted`, `test_case.moved`, link changes |
| Planning/execution | `plan.*`, `cycle.created/updated/started/closed/reopened`, `run.added/removed/assigned/version_updated/replaced`, `result.started/discarded/finalized/corrected`, `result.draft_taken_over` |
| Defects | `defect.created/updated/transitioned/linked/unlinked` |
| Requirements | `requirement.*`, `requirement.linked/unlinked` |
| Data | `import.committed`, `export.created`, `attachment.uploaded/deleted` |

Step-result edits during a draft are **not** individual audit events (too noisy); the finalize event stores the final step statuses, and the draft's step rows keep `updated_at/updated_by`.

### 13.2 Protection (BR-26)

- Insert-only at the database level (no UPDATE/DELETE privilege for the application role; trigger raises on update/delete). Retention purge (older than `audit_retention_years`) runs under a separate maintenance role and itself writes an audit event.
- P2: hash chain per organization (`prev_hash`, `hash`) and verification job (FR-AUD-005).

### 13.3 Views

- Record **History** tab on cases, plans, cycles, runs, defects, requirements.
- Project audit log (`project.audit.view`) and organization audit log (`org.audit.view`) with filters: actor, action, entity type, date range; CSV export.
- Access review export (FR-AUD-004): one row per user × scope: email, name, active, org admin, MFA enrolled, project, role, granted by, granted at, last sign-in.

## 14. End-to-end workflows

### W1 — First-time setup (UJ-1)
1. Deployment bootstrap command creates the first organization and Org Admin (CLI `tcms bootstrap --org "ACME" --admin-email ...`), which prints a one-time setup link.
2. Admin sets password and enrols MFA (mandatory for admins).
3. Admin sets organization security policy, invites users.
4. The Org Admin creates project SPARK (key `SPARK`, becoming its QA Manager) and invites Ayesha as QA Manager of SPARK; she adjusts environments (Dev, QA, Staging, UAT), creates release "SPARK v2.5" and adds members with roles.

### W2 — Import repository (UJ-2)
See §15.

### W3 — Author and review (UJ-3)
1. Engineer selects folder, presses `C` (new case). Inline editor: title, type, priority, preconditions, steps grid (Enter adds step, Tab moves between action/expected).
2. Save → v1 (`draft` if approval on, else `approved`).
3. Submit for review → reviewer notified.
4. Reviewer opens review panel: diff vs approved version, comments; Approve or Return.

### W4 — Plan and cycle (UJ-4)
1. Manager creates plan "SPARK v2.5 Regression" (type regression, release v2.5), adds cases by tag `regression` + folders, links requirements, sets exit criteria rules.
2. Lead creates cycle "Regression Cycle 01" from the plan, environment QA, dates.
3. Lead assigns: select folder "Web Application" → assign to Sana; "Backend Services" → Bilal; remaining left in pool.

### W5 — Execute (UJ-5)
1. Sana opens My Work → "Start" on Regression Cycle 01.
2. Runner opens first assigned run; she records steps with keys; failed step → actual result + pasted screenshot.
3. `D` raises defect prefilled; she saves it; returns to the run; `Ctrl+Enter` finishes (Failed); `Shift+N` opens next run.

### W6 — Defect and retest (UJ-6)
1. Lead triages SPARK-D-87 (severity high), assigns Omar.
2. Omar: In Progress → Fixed (fix version 2.5.1).
3. Lead: Ready for Retest → run flagged; Sana notified.
4. Sana retests run (attempt 2) → Passed → prompt → Verified → (Lead) Closed.

### W7 — Coverage review (UJ-7)
Hira opens Traceability, selects release v2.5, filters "not covered", links cases or creates tasks for QA (comment with @mention).

### W8 — Release readiness (UJ-8)
Ayesha opens release v2.5 → Readiness panel → rules evaluated → records `go_with_risks` with risks; Faisal (Viewer) sees decision and snapshot.

### W9 — Access review (UJ-9)
Zain opens Administration → Access review → exports XLSX.

## 15. Import and export (IMP)

### 15.1 Test case import (FR-IMP-001)

1. Upload CSV or XLSX (max 20 MB, max 5,000 cases, max 50,000 rows); choose sheet (XLSX).
2. **Map columns** to fields. Auto-mapping by header names (case-insensitive, synonyms e.g. "Summary" → title). Mappings can be saved per project as templates.
3. **Row model**: one row per step. A row with a non-empty case identifier column (`ID`, or `Title` when no ID column) starts a new case; subsequent rows with empty case columns are additional steps of that case. Alternatively, a single row per case with steps in one cell separated by numbered lines (`1.`) is supported (option).
4. **Folder**: a `Folder` column with path `Web Application/Authentication/Login` creates missing folders; else all cases go to the chosen target folder.
5. **Update mode**: if an `ID`/`Key` column matches an existing case key in the project, the case is updated (new version if content differs, metadata updated); otherwise created. Option: "create only" (matching keys rejected).
6. **Dry run** (always first): validates every row; shows counts (to create, to update, unchanged, errors) and a row-level error list (row, column, message). Commit is disabled while errors exist unless "skip rows with errors" is chosen.
7. **Commit**: background job; all-or-nothing transaction per file up to 5,000 cases; produces an import report (downloadable CSV with row → result/key). Audit `import.committed` with counts; each case also gets its own audit events tagged with the import ID.

Validation errors: unknown enum value (with allowed values listed), missing title, step without action, text too long, unknown owner email (falls back to importer with warning), folder path too deep, duplicate key in file.

### 15.2 Export (FR-IMP-002/003/004)

- Test cases: CSV/XLSX in the same row-per-step layout with a `Key` column so that the file re-imports as updates. Includes metadata, tags (comma-separated), latest version content (option: approved version).
- Requirements: one row per requirement + linked case keys.
- Defects, cycles/runs, results: per §11.5.
- Exports respect the user's permissions and current filters.

### 15.3 Requirements import (FR-IMP-003 / FR-REQ-003)

Same mapping flow; columns: key (update), title, description, type, priority, acceptance criteria, owner email, status, target release name, parent key, linked case keys (comma-separated).

**AC**

- AC-IMP-01: Given a 3,000-case XLSX with 2 invalid rows, when dry run executes, then the 2 rows are reported with row numbers and commit is disabled until "skip rows with errors" is chosen.
- AC-IMP-02: Given an export of 100 cases re-imported unchanged, then 0 cases are created, 0 versions created, 100 reported unchanged.
- AC-IMP-03: Given a commit failure mid-way (simulated), then no case from the file exists.

## 16. Integrations (Phase 2 — summary of required behaviour)

Detailed in [03 HLD §8](03-HLD.md); full functional spec written at Phase 2 start.

### 16.1 Jira (FR-INT-002..005)

- Connection: org-level, Jira Cloud site URL, auth (OAuth 2.0 3LO preferred; API token + email fallback), tested on save.
- Project mapping: TCMS project ↔ Jira project(s); issue type for defects; field mapping (summary, description, priority, severity custom field, environment, labels); status mapping Jira status → TCMS display status category (`to_do`, `in_progress`, `done`).
- Defects: "Create in Jira" from failed step creates a Jira issue (description with reproduction steps and a link back) and a TCMS defect record with `external_owner = jira`; its status, assignee and resolution are read-only in TCMS and refreshed by webhook (if available) or polling every 10 minutes and on view.
- Requirements: JQL-based import of stories/epics into read-only requirements (`source = jira`), refreshed every hour; deleted/unreachable issues marked "stale", never deleted.
- Links: test case ↔ Jira issue key with live summary/status card.
- Failures: sync errors shown on the connection page and on affected records; retries with backoff; never block saving TCMS data.

### 16.2 Automation (FR-AUTO-001..004)

- `POST /api/v1/automation/results` with an API token (`automation:submit` scope), multipart JUnit XML (or JSON schema), plus `project`, `cycle` (existing ID or name to create/reuse an automation cycle), `release`, `environment`, `build`, `ci_url`.
- Mapping: `<testcase classname="…" name="…">` → automation key `classname.name` (configurable pattern). Matched keys produce finalized attempts with `source = automation` on runs of the automation cycle (runs created on demand). Unmatched tests are listed in the import report for linking; optional "auto-create cases" project setting creates cases in a folder `Automation/<classname>`.
- Status mapping: pass → passed; failure/error → failed; skipped → skipped. Duration and failure message stored; system-out/err up to 1 MB stored as attachment.
- Automated results never modify manual cycles; reports can filter by source.
- Flaky detection: a case is **flaky** when, within its last 10 automated results on the same branch/environment, the status changed ≥ 3 times.
