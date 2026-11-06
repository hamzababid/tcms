# 10 — Implementation Backlog

| Field | Value |
| --- | --- |
| Version | 1.0 · 2026-11-03 |
| Depends on | [01 PRD](01-PRD.md), [02 Functional Spec](02-Functional-Specification.md), [09 Roadmap](09-Implementation-Roadmap.md) |

Epics map to roadmap milestones. Stories reference FR/BR/AC IDs; their acceptance criteria are the referenced ACs plus the bullets listed. Priority uses MoSCoW (M/S/C). Size: S (≤ 1 day), M (2–3 days), L (4–5 days) of generated-and-reviewed work.

Every story also meets the Definition of Done in [09 §7](09-Implementation-Roadmap.md).

---

## Epic overview

| Epic | Name | Milestone | Pri |
| --- | --- | --- | --- |
| E01 | Platform foundations | M0 | M |
| E02 | Identity and access | M1 | M |
| E03 | Workspace (org, projects, environments, releases) | M1 | M |
| E04 | Folders and repository | M2 | M |
| E05 | Test cases and versioning | M2 | M |
| E06 | Review workflow and case lifecycle | M2 | M |
| E07 | Test plans | M3 | M |
| E08 | Cycles and runs | M3 | M |
| E09 | Execution runner and results | M4 | M |
| E10 | Bug links (ADR-023) | M5 | S |
| E11 | Requirements and traceability | M6 | M |
| E12 | Search, filters, saved views | M6 | M |
| E13 | Dashboards, reports, readiness | M7 | M |
| E14 | Import and export | M8 | M |
| E15 | Audit and administration | M1 (core), M8 (UI) | M |
| E16 | Notifications and email | M7 | M |
| E17 | Hardening and release | M8–M9 | M |
| E20–E27 | Phase 2 epics | P2 | S |
| E30 | Phase 3 epic | P3 | C |

---

## E01 — Platform foundations (M0)

**Technical tasks:** monorepo layout; `pyproject.toml` (uv, ruff, mypy, pytest, import-linter contracts for module boundaries); FastAPI app factory, settings (Pydantic), structured logging, request ID middleware; SQLAlchemy engine/session, UoW; DomainError → problem+json handler; AccessContext/permissions registry; UUIDv7 ids, clock; pagination/filter/sort helpers with allow-lists; Alembic baseline (all MVP tables/enums/triggers/grants per [05](05-Database-Design.md)); job queue table + worker loop + scheduler + retry/dead-letter; audit recorder; S3 client + attachment service skeleton; health endpoints; Docker images (backend multi-stage, web nginx); docker-compose (db, minio + bucket init, mailpit, api, worker, web); Makefile; CI workflow with gates; frontend scaffold (Vite, TS strict, Tailwind, shadcn, TanStack Router/Query, openapi-typescript client, AppShell placeholder, StatusBadge, ProgressBar, Metric); seed CLI skeleton; testcontainers fixtures, factories, frozen clock.

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-001 | As a developer, I can start the full stack with one command so that I can work locally | M | M | NFR-MNT-05 | `make up` + `make migrate` + `make seed` < 10 min; web on :5173, api on :8000, mailpit UI available |
| US-002 | As a developer, every error is returned as problem+json with a stable code | M | S | 06 §3 | Unknown route, validation error, DomainError subclasses map correctly; request_id present |
| US-003 | As a developer, the DB enforces immutability of versions, final results and audit | M | M | BR-06, BR-26, 05 §4 | SQL tests: UPDATE/DELETE raise; approval columns settable once |
| US-004 | As a developer, background jobs run with retry and dead-letter | M | M | NFR-REL-02 | Failing job retried with backoff, then `dead`; dedupe key prevents duplicates |
| US-005 | As a developer, the frontend API client is generated from OpenAPI and CI fails on drift | M | S | NFR-MNT-03 | Changing a schema without regenerating fails CI |
| US-006 | As a developer, module boundaries are enforced | M | S | 03 §5.2 | import-linter contract fails on a forbidden import |

## E02 — Identity and access (M1)

**Technical tasks:** Argon2id hashing; common-password list; sessions table + cookie handling; CSRF double submit; login/MFA/lockout/rate limit; TOTP (pyotp) with encrypted secrets (AES-GCM, key rotation prefix); recovery codes; reset tokens; invitations; API tokens; permission resolution with per-request cache; `project_context_from` dependency; authz matrix harness; frontend auth screens and `usePermission`.

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-010 | As a user, I sign in with email and password | M | M | FR-AUTH-001 | AC-AUTH-01, AC-AUTH-02; TCMS-001/002 |
| US-011 | As a user, my account locks after repeated failures | M | S | FR-AUTH-007, NFR-SEC-04 | AC-AUTH-03 |
| US-012 | As a user, I enrol TOTP MFA and receive recovery codes | M | M | FR-AUTH-002/003 | QR + secret shown; codes shown once; TCMS-005/006 |
| US-013 | As an Org Admin, I am forced to enrol MFA; as an admin I can require MFA for all | M | S | FR-AUTH-002 | AC-AUTH-04 |
| US-014 | As a user, I reset a forgotten password by email | M | M | FR-AUTH-004 | AC-AUTH-07; TCMS-007 |
| US-015 | As an admin, I invite users by email with optional project role | M | M | FR-AUTH-005 | TCMS-008; invitation expires after 7 days |
| US-016 | As a user, my session expires on idle/absolute timeout; I can sign out and see/revoke my sessions | M | M | FR-AUTH-006 | AC-AUTH-06 |
| US-017 | As a user, I create, view and revoke personal API tokens | M | M | FR-AUTH-010 | Token shown once; scope enforced (TCMS-010) |
| US-018 | As the system, permissions resolve from project roles and org admin flag | M | M | FR-AUTH-008/009 | Seeded roles per [02 §3.2](02-Functional-Specification.md); authz matrix for M1 routes (TCMS-012) |
| US-019 | As the system, non-members get 404 and other orgs' data is invisible | M | M | NFR-SEC-05 | TCMS-013 |

## E03 — Workspace (M1)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-020 | As an Org Admin, I bootstrap the first organization via CLI | M | S | W1 | `tcms bootstrap` prints one-time setup link |
| US-021 | As an Org Admin, I edit organization settings and security policy | M | S | 02 §4.1 | Validation ranges; audit `organization.updated` |
| US-022 | As a QA Manager, I create a project with a key | M | M | FR-WS-002, BR-27 | AC-WS-01; creator is QA Manager; QA/Staging environments created; key sequences created |
| US-023 | As a QA Manager, I configure project options | M | S | FR-WS-004 | Settings effects verified in later epics; audit |
| US-024 | As a QA Manager, I manage project members and roles | M | M | FR-WS-003, BR-29 | Default Viewer; cannot remove last QA Manager |
| US-025 | As a QA Manager, I manage environments | M | S | FR-WS-005 | AC-WS-03 |
| US-026 | As a QA Manager, I manage releases and their status | M | S | FR-WS-006 | Valid transitions only |
| US-027 | As a user, I switch projects and see the app shell | M | M | 07 §3 | Project switcher, breadcrumbs, sidebar collapse persisted |
| US-028 | As a member, I see the project activity feed | M | S | FR-WS-007 | Rendered audit summaries, filter by type/user |
| US-029 | As a QA Manager, I archive and restore a project | M | S | 02 §4.2 | AC-WS-02 |

## E04 — Folders and repository (M2)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-040 | As a QA Lead, I create, rename and reorder folders | M | M | FR-TD-001 | Sibling name uniqueness; depth ≤ 10 |
| US-041 | As a QA Lead, I move folders (drag and drop) | M | M | FR-TD-001 | AC-TD-01/02; path/depth of subtree updated |
| US-042 | As a QA Lead, I archive/restore and delete empty folders | M | S | BR-15 | AC-TD-03 |
| US-043 | As a QA user, I browse the tree with counts and list cases with filters | M | L | FR-SRCH-002 | Counts include descendants; tree 2,000 folders < 1 s |
| US-044 | As a QA user, I perform bulk operations on cases | M | L | FR-TD-010 | > 200 → job; per-case audit with bulk id (TCMS-043) |
| US-045 | As a QA user, I manage tags including system tags | M | S | FR-TD-008 | System tags exist per project; validation of tag names |

## E05 — Test cases and versioning (M2)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-050 | As a QA Engineer, I create a steps-format case with the step grid | M | L | FR-TD-002 | Keyboard flow (TCMS-046); key allocated; v1 |
| US-051 | As a QA Engineer, I create a text-format case | M | S | FR-TD-002 | text_body required |
| US-052 | As a QA Engineer, editing content creates a new version; metadata edits do not | M | M | BR-01/02 | AC-TD-10/11/13 |
| US-053 | As a QA user, I view version history and compare versions | M | L | FR-TD-004 | AC-TD-12; step alignment diff |
| US-054 | As a QA Engineer, I restore an older version | M | S | FR-TD-005 | New version created |
| US-055 | As a QA Engineer, I attach files to cases and steps and paste images into Markdown | M | M | FR-TD-011 | Limits and types enforced; carried forward (TCMS-045) |
| US-056 | As a QA user, I comment on cases and @mention colleagues | M | M | 02 §9.1 | Mention notification; 15-min edit window |
| US-057 | As a QA Engineer, I link related cases and duplicate a case | M | S | FR-TD-009/012 | TCMS-044 |
| US-058 | As a QA user, I see a case's executions and history | M | M | FR-TD-013 | Runs across cycles with versions |
| US-059 | As a QA user, conflicting edits are detected | M | S | BR-25 | Conflict dialog (TCMS-047) |
| US-060 | As a QA Engineer, I record automation status and keys | M | S | FR-TD-014 | Keys unique per project |

## E06 — Review workflow and lifecycle (M2)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-065 | As a QA Engineer, I submit a case for review | M | S | FR-TD-006 | Status in_review; reviewer notified |
| US-066 | As a QA Lead, I approve or return a case with comments | M | M | FR-TD-006, BR-18 | AC-TD-20/21/22 |
| US-067 | As a QA Manager, enabling/disabling approval handles existing cases | M | S | 02 §5.4 | Grandfathering (TCMS-040) |
| US-068 | As a QA Lead, I deprecate, archive and restore cases | M | S | FR-TD-007, BR-13 | TCMS-041 |
| US-069 | As a QA Manager, I hard-delete a never-run case | M | S | BR-14 | TCMS-042; confirm by typing key |

## E07 — Test plans (M3)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-070 | As a QA Manager, I create a plan with objectives, scope, environments, criteria, risks, dates, members | M | M | FR-PLN-001 | All fields validated; exit rules saved as structured rules |
| US-071 | As a QA Manager, I add cases to a plan by folder, tag, saved view or search | M | M | FR-PLN-002 | TCMS-051 (exclusions reported) |
| US-072 | As a QA Manager, I link requirements to a plan | M | S | FR-PLN-003 | (Enabled fully after E11) |
| US-073 | As a QA Manager, I clone a plan | M | S | FR-PLN-006 | Copy without cycles |
| US-074 | As a QA user, I view plan cases with latest results per cycle | M | M | 02 §6.2 | Columns per cycle |

## E08 — Cycles and runs (M3)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-080 | As a QA Lead, I create a cycle from a plan or the repository | M | L | FR-EXE-001/002, BR-03 | AC-PLN-01; > 500 runs via job (TCMS-054) |
| US-081 | As a QA Lead, I add and remove cases in a cycle | M | M | FR-EXE-003, BR-12 | TCMS-057 |
| US-082 | As a QA Lead, I assign runs individually, in bulk or leave them in a pool; testers can claim | M | M | FR-EXE-004 | TCMS-055/056 |
| US-083 | As a QA Lead, I see cycle progress by status, assignee and folder | M | M | FR-EXE-013 | Numbers equal ExecutionSummary |
| US-084 | As a QA Lead, I start, close, reopen, clone and archive cycles | M | M | FR-EXE-012, BR-11 | TCMS-058/059/060 |
| US-085 | As a QA Lead, I sync a cycle with its plan | M | S | BR-31 | AC-PLN-02 |
| US-086 | As a QA Lead, I update not-run runs to the latest version or replace runs with results | M | M | FR-EXE-011, BR-04/05 | TCMS-082/083 |
| US-087 | As a QA Lead, I reorder runs | M | S | 02 §7.1 | Drag or sort by folder/priority |

## E09 — Execution runner and results (M4)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-090 | As a QA Engineer, I start an attempt and record step results with auto-save | M | L | FR-EXE-005/006 | Step save p95 < 200 ms; save indicator |
| US-091 | As a QA Engineer, the run status is derived when I finish | M | M | FR-EXE-007, BR-08/09 | Roll-up matrix (TCMS-071); AC-EXE-01/02/03 |
| US-092 | As a QA Engineer, I block/skip/mark N/A a run with a reason | M | S | FR-EXE-008, BR-10 | TCMS-074 |
| US-093 | As a QA Engineer, I attach evidence and paste screenshots per step | M | M | FR-EXE-006 | TCMS-087 |
| US-094 | As a QA Engineer, I use the keyboard and move to the next run automatically | M | M | NFR-UX-01 | TCMS-086 |
| US-095 | As a QA Engineer, I retest a run, keeping the history | M | M | FR-EXE-009 | AC-EXE-07 |
| US-096 | As a QA Lead, I correct a finalized result with a reason | M | S | FR-EXE-010 | TCMS-080 |
| US-097 | As the system, final results cannot be changed and only one draft exists per run | M | M | BR-06/07 | AC-EXE-04/05; TCMS-090 |
| US-098 | As a QA Engineer, I execute text-format cases | M | S | 02 §7.3 | TCMS-089 |
| US-099 | As a QA Engineer, I see My Work across projects | M | M | FR-EXE-014 | Grouped by cycle with counts and retest flags |
| US-100 | As a QA Engineer, I see when a newer case version exists and update if allowed | M | S | BR-04 | AC-EXE-08 |

## E10 — Bug links (M5; ADR-023 replaced the internal defect workflow)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-110 | As a QA Engineer, I link the bug I logged in our tracker to a failed step from the runner | M | M | FR-DEF-001, BR-20 | AC-BUG-01, TCMS-100 |
| US-111 | As a QA Manager, I set the project's tracker name and bug address template | M | S | FR-DEF-002 | AC-BUG-02 |
| US-112 | As a user, I see bug chips on the run, its history, the cycle runs and the case | M | M | FR-DEF-003 | TCMS-100, 102 |
| US-113 | As a QA Engineer, I link a bug directly to a case | M | S | FR-DEF-001 | TCMS-102 |
| US-114 | As a QA Lead, I mark a bug ready for retest so its linked runs are flagged | M | M | BR-21 | AC-BUG-03, TCMS-103/104 |
| US-115 | As a QA Engineer, I copy a ready-to-paste bug report from a failed attempt | M | S | FR-DEF-005 | Copy bug details |
| US-116 | As a user, I see a project Bugs list grouped by reference | M | M | FR-DEF-006 | TCMS-105 |
| US-117 | As a QA Manager, I can require a bug link on every failed result | M | S | FR-DEF-004 | AC-BUG-04, TCMS-106 |

## E11 — Requirements and traceability (M6)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-120 | As a PM, I create requirements with hierarchy and acceptance criteria | M | M | FR-REQ-001 | Parent depth ≤ 5; no cycles |
| US-121 | As a PM or QA, I link requirements and cases from either side and in bulk | M | M | FR-REQ-002 | TCMS-110 |
| US-122 | As a PM, I see coverage and status per release | M | L | FR-REQ-005, BR-23 | AC-REQ-01..04; property test |
| US-123 | As a PM, I use the traceability matrix with filters and export | M | L | FR-REQ-004 | TCMS-112 |

## E12 — Search, filters, saved views (M6)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-130 | As a user, I search globally by key or text | M | M | FR-SRCH-001 | TCMS-118/119; < 500 ms p95 |
| US-131 | As a user, I use consistent filters on every list | M | M | FR-SRCH-002 | Operators per 02 §12 |
| US-132 | As a user, I save private or shared views and set defaults | M | M | FR-SRCH-003 | TCMS-120 |
| US-133 | As a user, I use the command palette | M | S | 07 §4.3 | `>` actions |

## E13 — Dashboards, reports, readiness (M7)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-140 | As the system, all metrics come from one definitions module | M | M | BR-24, ADR-013 | Property test vs oracle (TCMS-113/114) |
| US-141 | As a QA Manager, I use the manager dashboard with filters | M | L | FR-RPT-001 | Widgets per 02 §11.3; < 2 s |
| US-142 | As a QA Engineer, I use my dashboard | M | S | FR-RPT-002 | 02 §11.3 |
| US-143 | As a manager, I see quality trends from daily snapshots | M | L | FR-RPT-003 | Snapshot job; trend charts with data tables |
| US-144 | As a user, I run the six standard reports and export CSV/XLSX | M | L | FR-RPT-004/005 | Large exports via job; formula injection protection (TCMS-117) |
| US-145 | As a QA Manager, I see release readiness and record a decision | M | M | FR-RPT-006 | TCMS-116 |
| US-146 | As an Org Admin, I see the organization dashboard | M | S | FR-WS-008 | Projects limited by membership unless admin |

## E14 — Import and export (M8)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-150 | As a QA Lead, I import cases from CSV/XLSX with mapping, dry run and commit | M | L | FR-IMP-001 | AC-IMP-01/03; 5,000 cases < 2 min |
| US-151 | As a QA Lead, I save and reuse mapping templates | M | S | 02 §15.1 | Templates per project |
| US-152 | As a QA user, I export cases in re-importable format | M | M | FR-IMP-002 | AC-IMP-02 |
| US-153 | As a PM, I import/export requirements | M | M | FR-IMP-003 | Links to case keys created |
| US-154 | As a user, I export bug links, cycles and results | M | S | FR-IMP-004 | Via reports (E13) |

## E15 — Audit and administration (M1 core, M8 UI)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-160 | As the system, every state change writes an audit event in the same transaction | M | M | FR-AUD-001, BR-26 | TCMS-130/132 |
| US-161 | As a user, I see a record's history | M | M | FR-AUD-002 | Changes old → new rendered |
| US-162 | As an admin/manager, I search and export the audit log | M | M | FR-AUD-002 | Filters; CSV |
| US-163 | As an Org Admin, I export an access review | M | S | FR-AUD-004 | TCMS-133 |
| US-164 | As an Org Admin, I manage users (deactivate, reset MFA, revoke sessions, admin flag) | M | M | 02 §3.5 | TCMS-011; last admin protected |
| US-165 | As an Org Admin, I see system status and retry dead jobs | M | S | 03 §15 | TCMS-139 |
| US-166 | As the system, audit retention purge runs monthly under maintenance role | M | S | NFR-CMP-01 | Purge writes its own event |

## E16 — Notifications and email (M7)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-170 | As a user, I receive in-app notifications for the events in 02 §2.7 | M | M | 02 §2.7 | Bell count; mark read |
| US-171 | As a user, I receive emails (assignment digest, mentions) and can opt out | M | M | 02 §2.7 | Templates; opt-out respected |

## E17 — Hardening and release (M8–M9)

| ID | Story | Pri | Size | Refs | Acceptance |
| --- | --- | --- | --- | --- | --- |
| US-180 | As an operator, I deploy with production compose and Caddy TLS | M | M | 03 §12 | Runbook verified on staging |
| US-181 | As an operator, nightly backups run and restore is rehearsed | M | M | NFR-REL-03 | TCMS-141 |
| US-182 | As a team, performance meets NFR-PERF on the large seed | M | L | NFR-PERF | TCMS-142 |
| US-183 | As a team, security checks pass (ZAP, ASVS L2 review, dependencies) | M | L | NFR-SEC | No high findings |
| US-184 | As a team, accessibility passes (axe + manual) | M | M | NFR-UX-03 | No serious issues |
| US-185 | As SPARK QA, we complete the pilot and go live | M | L | MVP gate | 08 §12 exit |

---

## Phase 2 epics (summary; stories refined at phase start)

| Epic | Name | Key stories |
| --- | --- | --- |
| E20 | Jira Cloud connector (P2.1) | Connect Jira (OAuth/API token); map projects, issue types, fields, statuses; link cases/requirements to issues; create Jira defect from failed result; mirror status via webhook/poll; import stories as requirements; sync error console |
| E21 | OIDC SSO (P2.2) | Configure IdP; SSO sign-in; SSO-required policy with break-glass |
| E22 | Automation results (P2.3) | Token scope; JUnit/JSON upload; automation cycles; key mapping and unmatched linking; artifacts; automation dashboard; flaky detection |
| E23 | Reuse (P2.4) | Shared steps with versions and adopt flow; parameters/datasets; configuration matrices |
| E24 | Roles and custom fields (P2.5) | Role editor; custom fields on cases |
| E25 | Advanced reporting (P2.6) | PDF reports; historical RTM; advanced execution analytics |
| E26 | Formats (P2.7) | Exploratory sessions; data-validation checks |
| E27 | Audit hash chain (P2.8) | Chain + verification job |

## Phase 3 epic

| Epic | Name | Items |
| --- | --- | --- |
| E30 | Intelligence and breadth | AI case generation/review, duplicate detection, risk-based prioritization, coverage gap analysis, BDD, more trackers, migration importers, SCIM, i18n |
