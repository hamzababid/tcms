# 01 — Product Requirements Document (PRD)

| Field | Value |
| --- | --- |
| Product | TCMS — Test Case Management System (working name) |
| Version | 1.0 (specification baseline) |
| Date | 2026-11-03 |
| Status | Baseline for implementation |
| Related | [02 Functional Spec](02-Functional-Specification.md) · [03 HLD](03-HLD.md) · [06 API](06-API-Specification.md) · [11 Decision Log](11-Decision-Log.md) |

This document says **what** the product must do and **why**. The functional specification says exactly **how it behaves**. Requirement IDs defined here (`FR-*`, `NFR-*`, `BR-*`) are referenced by every other document, the backlog and the tests.

---

## 1. Product vision

A self-hosted, internally owned test management platform that lets a QA organization design, version, plan, execute and report on testing — with results that can be trusted in an audit — and that connects cleanly to Jira and CI pipelines without depending on them.

**Product principles**

1. **History is sacred.** Recorded execution results and audit records are never edited or deleted. Corrections are new records.
2. **Derived numbers are computed, never typed.** Run status, coverage and every metric are computed from records using the rules in this document.
3. **Metrics cannot mislead.** Every rate is shown with its numerator and denominator; untested work is never hidden.
4. **Fast for the tester.** The authoring and execution screens are optimized for keyboard use and minimal page changes.
5. **Works alone, connects cleanly.** The core works without Jira or CI; integrations attach through connectors with explicit ownership of each entity.
6. **Boring technology.** One deployable application, PostgreSQL, object storage. No component without a clear need.

## 2. Business objectives

| ID | Objective | Measure (12 months after MVP go-live) |
| --- | --- | --- |
| OBJ-1 | Replace spreadsheets and ad-hoc tracking for SPARK QA | 100% of SPARK regression and release-validation cycles run in TCMS |
| OBJ-2 | Release decisions based on reliable quality data | Every SPARK release has a recorded go/no-go decision based on the readiness panel |
| OBJ-3 | Requirements traceability | ≥ 90% of in-scope requirements per release linked to at least one test case |
| OBJ-4 | Audit readiness (ISO 27001, SOC 2) | Access reviews and change evidence exported from TCMS without manual reconstruction |
| OBJ-5 | Lower tool cost | No per-seat licence for test management |
| OBJ-6 | Maintainability | Platform maintained by 1 frontend + 1 backend developer; CI green on main ≥ 95% of days |

## 3. Context and constraints (from discovery)

| Topic | Decision |
| --- | --- |
| Product type | Internal-first, SaaS-ready. `organization_id` on every tenant-owned record. No billing or self-service signup. |
| Builders | Code generated with Claude Code; maintained afterwards by 1 FE + 1 BE developer. |
| Deployment | Self-hosted with Docker; cloud-ready (S3-compatible storage, env-based config). |
| Scale (year 1) | 1–5 organizations, ~50 users, ~10,000 cases per project, ~50,000 executions per year. Design headroom: 10× each. |
| Compliance | ISO 27001 and SOC 2 evidence support. |
| Migration | CSV/Excel import of test cases (and requirements). No history migration. |
| Jira | Used by developers and product managers. Narrow connector at the start of Phase 2. Assumed Jira Cloud. |
| Authentication | Email + password + TOTP MFA in MVP; OIDC SSO in Phase 2. |
| Case approval | Configurable per project, off by default. |
| Version pinning | Runs pin the case version they were created with. |
| Configurations | Environments in MVP; configuration matrices and parameters in Phase 2. |
| "Passed with exceptions" | Not a status. A run passes with skipped steps flagged. |
| Reuse | Shared steps within a project, Phase 2. No cross-project sharing. |
| Automation | JUnit XML first (Phase 2) plus a generic JSON results API. |

## 4. Target users and personas

### 4.1 Roles

| Role | Scope | Summary |
| --- | --- | --- |
| Organization Administrator | Organization | Manages users, roles, organization settings, integrations; implicit admin on all projects |
| QA Manager | Project | Owns test strategy, plans, cycles, reporting, release readiness |
| QA Lead | Project | Organizes the repository, reviews cases, assigns and monitors execution |
| QA Engineer | Project | Writes and executes cases, records evidence, reports and retests defects |
| Developer | Project | Reads cases and evidence, works defects through to Fixed |
| Product Manager / Business Analyst | Project | Owns requirements, links them to cases, reviews coverage |
| Viewer (Management) | Project | Read-only dashboards and reports |

The permission model is defined in [02 Functional Spec §3](02-Functional-Specification.md#3-identity-and-access-auth).

### 4.2 Personas

**Ayesha — QA Manager (primary).** Runs testing for SPARK releases. Needs to know at any moment what is tested, what failed, what blocks the release, and to defend a go/no-go decision. Frustrated by pass rates that look good because half the suite was never run.

**Bilal — QA Lead (primary).** Keeps 4,000 cases organized, reviews new cases, assigns a 250-case regression to five testers every two weeks. Needs bulk operations and a clear view of who is behind.

**Sana — QA Engineer (primary).** Executes 40–60 manual cases per day. Wants to stay on one screen, use the keyboard, paste screenshots, and raise a complete defect in seconds.

**Omar — Developer (secondary).** Opens defects from Jira or TCMS, wants exact reproduction steps, the case version, environment, build and screenshots — without asking QA.

**Hira — Product Manager (secondary).** Wants to see which acceptance criteria are verified for the upcoming release and which have no tests.

**Faisal — Head of Engineering (viewer).** Wants a release readiness summary he can trust and trends across releases.

**Zain — Org Administrator / IT.** Onboards users, enforces MFA, produces quarterly access reviews for the ISO 27001 auditor.

## 5. User journeys (summary)

Full step-by-step workflows are in [02 Functional Spec §14](02-Functional-Specification.md#14-end-to-end-workflows); screens in [07 UI/UX](07-UI-UX-Specification.md).

| ID | Journey | Primary persona | Outcome |
| --- | --- | --- | --- |
| UJ-1 | First-time setup: create organization, invite users, enable MFA, create project SPARK, environments, release | Zain, Ayesha | Project ready for content |
| UJ-2 | Import 3,000 existing cases from Excel into a folder tree | Bilal | Repository populated, import report reviewed |
| UJ-3 | Author and review a test case | Sana → Bilal | Approved version available to cycles |
| UJ-4 | Plan release SPARK v2.5 and create Regression Cycle 01 (250 cases) with assignments | Ayesha, Bilal | Testers see their work |
| UJ-5 | Execute assigned runs, record step results and evidence | Sana | Results recorded |
| UJ-6 | Raise a defect from a failed step; developer fixes; tester retests and verifies | Sana → Omar → Sana | Defect closed with full trail |
| UJ-7 | Review requirement coverage for a release | Hira | Gap list of untested requirements |
| UJ-8 | Assess release readiness and record go/no-go | Ayesha → Faisal | Auditable release decision |
| UJ-9 | Quarterly access review export | Zain | Evidence file for auditor |
| UJ-10 (P2) | CI uploads JUnit XML; results appear against linked cases | QA Automation | Automated results visible beside manual |
| UJ-11 (P2) | Raise defect into Jira from a failed run; see Jira status in TCMS | Sana, Omar | One defect record, no double entry |

## 6. Functional requirements

Priority: **M** = Must (MVP), **S** = Should (Phase 2), **C** = Could (Phase 3). Module codes: AUTH, WS (workspace), TD (test design), PLN (planning), EXE (execution), DEF (defects), REQ (requirements), RPT (reporting), SRCH (search), AUD (audit), IMP (import/export), ADM (administration), INT (integrations), AUTO (automation).

### 6.1 Identity and access — AUTH

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-AUTH-001 | Users sign in with email and password. | M |
| FR-AUTH-002 | Users can enrol TOTP MFA; organizations can require MFA for all users; MFA is always required for Organization Administrators. | M |
| FR-AUTH-003 | Users receive one-time recovery codes on MFA enrolment and can regenerate them. | M |
| FR-AUTH-004 | Password reset via emailed single-use, time-limited link. | M |
| FR-AUTH-005 | Users are added by invitation (email link, 7-day expiry); no self-registration. | M |
| FR-AUTH-006 | Sessions expire after configurable idle and absolute timeouts; users can sign out; admins can revoke a user's sessions. | M |
| FR-AUTH-007 | Account lockout after repeated failed sign-ins. | M |
| FR-AUTH-008 | Role-based access control with permissions bundled into roles, granted at organization or project scope. | M |
| FR-AUTH-009 | Seven predefined roles (Org Admin, QA Manager, QA Lead, QA Engineer, Developer, PM/BA, Viewer). | M |
| FR-AUTH-010 | Personal API tokens (scoped, expiring, revocable) for API and CI access. | M |
| FR-AUTH-011 | Custom roles via a role editor. | S |
| FR-AUTH-012 | OIDC single sign-on (Entra ID, Google, Okta) with optional enforcement. | S |
| FR-AUTH-013 | SCIM user provisioning. | C |

### 6.2 Workspace — WS

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-WS-001 | An organization contains users, projects and organization settings. | M |
| FR-WS-002 | Create, edit and archive projects with a unique project key (e.g. `SPARK`). | M |
| FR-WS-003 | Manage project members and their project role. | M |
| FR-WS-004 | Project settings: approval required, self-approval allowed, only-assignee-executes, module depth for reports, attachment limits. | M |
| FR-WS-005 | Manage environments per project (e.g. Dev, QA, Staging, UAT). | M |
| FR-WS-006 | Manage releases per project with dates and status (planned, active, released, archived). | M |
| FR-WS-007 | Project activity feed. | M |
| FR-WS-008 | Organization dashboard listing projects with headline quality figures. | M |

### 6.3 Test design and repository — TD

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-TD-001 | Hierarchical folders (max depth 10) per project: create, rename, move, archive, delete (empty only), reorder. | M |
| FR-TD-002 | Create test cases with the fields defined in the functional spec, in **Steps** or **Text** format. | M |
| FR-TD-003 | Every content change creates a new immutable version; metadata changes are audited without a new version. | M |
| FR-TD-004 | View version history and compare any two versions side by side. | M |
| FR-TD-005 | Restore a previous version (creates a new version with that content). | M |
| FR-TD-006 | Optional review workflow: submit, approve, return with comments; enforced per project. | M |
| FR-TD-007 | Lifecycle statuses: Draft, In Review, Approved, Deprecated, Archived. | M |
| FR-TD-008 | Tags (free and system tags `smoke`, `sanity`, `regression`). | M |
| FR-TD-009 | Duplicate a case (new key, version 1, link "duplicated from"). | M |
| FR-TD-010 | Bulk operations: move, tag/untag, set priority/type/owner, archive, restore, export. | M |
| FR-TD-011 | Attachments on cases and on individual steps. | M |
| FR-TD-012 | Related-case links. | M |
| FR-TD-013 | Case execution history: every run and result across cycles. | M |
| FR-TD-014 | Automation status and automation keys on cases. | M |
| FR-TD-015 | Shared step blocks, versioned, adopted explicitly by cases. | S |
| FR-TD-016 | Parameters / datasets producing parameterized runs. | S |
| FR-TD-017 | Exploratory charter format and session execution. | S |
| FR-TD-018 | Data-validation format (checks with input, rule, expected value, tolerance). | S |
| FR-TD-019 | Custom fields on test cases. | S |
| FR-TD-020 | BDD/Gherkin format. | C |
| FR-TD-021 | AI-assisted case generation and review; duplicate detection. | C |

### 6.4 Planning — PLN

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-PLN-001 | Create test plans with type, release, objectives, scope (in/out), environments, entry/exit criteria, risks, timeline, acceptance criteria, assigned QA members. | M |
| FR-PLN-002 | Select cases into a plan by folder, tag, filter or individually. | M |
| FR-PLN-003 | Link requirements to a plan. | M |
| FR-PLN-004 | Generate one or more cycles from a plan; a plan is reusable across cycles. | M |
| FR-PLN-005 | Exit criteria are recorded as structured readiness rules (see FR-RPT-006). | M |
| FR-PLN-006 | Clone a plan. | M |

### 6.5 Execution — EXE

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-EXE-001 | Create a cycle from a plan or directly from the repository, with release, environment, dates and description. | M |
| FR-EXE-002 | A cycle contains one run per selected case, pinned to a case version. | M |
| FR-EXE-003 | Add and remove cases (removal only for runs without results). | M |
| FR-EXE-004 | Assign runs to testers individually or in bulk; leave runs unassigned in a team pool that testers can claim. | M |
| FR-EXE-005 | Execute runs one at a time or in sequence ("next run") on a single execution screen. | M |
| FR-EXE-006 | Record step status, actual result, comment and evidence per step; auto-save. | M |
| FR-EXE-007 | Run status derived from step results by the roll-up rules (BR-08, BR-09). | M |
| FR-EXE-008 | Mark a whole run Blocked, Skipped or Not Applicable with a mandatory reason. | M |
| FR-EXE-009 | Retest: add a new result attempt to the same run; previous attempts remain. | M |
| FR-EXE-010 | Correct a finalized result by recording a new attempt that references it. | M |
| FR-EXE-011 | "Update to latest version" on runs without results; "Replace run" on runs with results. | M |
| FR-EXE-012 | Cycle lifecycle: Planned, Active, Closed; reopen with permission and reason. | M |
| FR-EXE-013 | Cycle progress view by status, assignee and folder. | M |
| FR-EXE-014 | "My Work": runs assigned to me across projects. | M |
| FR-EXE-015 | Retest flags on runs linked to defects that are Ready for Retest. | M |
| FR-EXE-016 | Configuration matrices (one run per case × configuration). | S |

### 6.6 Defects — DEF

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-DEF-001 | Create defects with the fields in the functional spec. | M |
| FR-DEF-002 | Create a defect from a failed step, pre-filled from the run. | M |
| FR-DEF-003 | Link a defect to many results and cases; link an existing defect to a result. | M |
| FR-DEF-004 | Lifecycle state machine with role-restricted transitions (BR-19). | M |
| FR-DEF-005 | Comments, attachments and status history on defects. | M |
| FR-DEF-006 | Defect list with filters, saved views, bulk transition and assignment. | M |
| FR-DEF-007 | Create the defect in Jira and mirror its status (Jira as owner). | S |

### 6.7 Requirements and traceability — REQ

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-REQ-001 | Create and edit requirements with type, priority, acceptance criteria, owner, status, target release, optional parent. | M |
| FR-REQ-002 | Link requirements and cases many-to-many. | M |
| FR-REQ-003 | Import requirements from CSV/Excel. | M |
| FR-REQ-004 | Traceability matrix per release: requirement → cases → latest results → defects. | M |
| FR-REQ-005 | Coverage metrics (BR-23). | M |
| FR-REQ-006 | Import Jira issues as read-only mirrored requirements. | S |
| FR-REQ-007 | Advanced RTM: historical coverage per release, export to PDF. | S |
| FR-REQ-008 | AI-assisted coverage gap analysis. | C |

### 6.8 Reporting — RPT

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-RPT-001 | QA Manager dashboard (metrics listed in functional spec §11). | M |
| FR-RPT-002 | QA Engineer dashboard ("My Work"). | M |
| FR-RPT-003 | Project quality dashboard with trends. | M |
| FR-RPT-004 | Reports filterable by date, release, cycle, module, tester. | M |
| FR-RPT-005 | Export reports and lists to CSV and Excel. | M |
| FR-RPT-006 | Release readiness panel evaluating structured exit criteria; go/no-go decision record. | M |
| FR-RPT-007 | PDF report export. | S |
| FR-RPT-008 | Advanced execution analytics (tester throughput, time per case, failure hotspots). | S |
| FR-RPT-009 | Automation coverage and flaky-test analytics. | S (basic) / C (advanced) |

### 6.9 Search — SRCH

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-SRCH-001 | Global search across case keys/titles, folders, requirements, defects, cycles, plans and external keys. | M |
| FR-SRCH-002 | Advanced filters on every list, sorting, pagination. | M |
| FR-SRCH-003 | Saved views (private or shared within a project). | M |

### 6.10 Audit — AUD

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-AUD-001 | Append-only audit trail of every create, change (old and new values), approval, execution, transition, permission change and configuration change. | M |
| FR-AUD-002 | Per-record history view and project/organization audit log with filters and export. | M |
| FR-AUD-003 | Security events: sign-in success/failure, MFA changes, token creation/revocation, role grants. | M |
| FR-AUD-004 | Access review export (user, scope, role, granted by/at, last sign-in, MFA status). | M |
| FR-AUD-005 | Tamper-evident hash chain on audit events. | S |

### 6.11 Import/export — IMP

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-IMP-001 | Import test cases from CSV/XLSX with column mapping, folder creation, multi-row steps, dry-run preview and error report. | M |
| FR-IMP-002 | Export cases (with steps) to CSV/XLSX in a re-importable format. | M |
| FR-IMP-003 | Import/export requirements. | M |
| FR-IMP-004 | Export defects, cycles and run results. | M |
| FR-IMP-005 | Import from TestRail/Zephyr export formats. | C |

### 6.12 Integrations and automation — INT, AUTO

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-INT-001 | Connector framework: connections, credentials stored encrypted, external links, sync jobs with retry. | S (architecture in MVP) |
| FR-INT-002 | Jira Cloud connection (OAuth 2.0 3LO or API token) and project mapping. | S |
| FR-INT-003 | Link cases and requirements to Jira issues; show live issue summary. | S |
| FR-INT-004 | Create Jira issue from a failed result; mirror status one-way. | S |
| FR-INT-005 | Import Jira stories as read-only requirements; refresh on schedule. | S |
| FR-INT-006 | Additional trackers (Azure Boards, GitLab Issues). | C |
| FR-AUTO-001 | Upload JUnit XML results with an API token; map to cases via automation keys. | S |
| FR-AUTO-002 | Generic JSON results API. | S |
| FR-AUTO-003 | Store logs and artifacts from automated runs. | S |
| FR-AUTO-004 | Automation pass-rate and flaky-test detection (status flips across recent runs). | S basic / C advanced |

## 7. Business rules

These rules are normative. The functional specification expands each one; the database and API enforce them; the QA strategy tests each one.

| ID | Rule |
| --- | --- |
| BR-01 | A change to test **content** (title, description, preconditions, test data, postconditions, overall expected result, steps, text body, format) creates a new immutable version. A change to **metadata** (folder, type, priority, owner, reviewer, tags, automation fields) does not; it is audited. |
| BR-02 | Version numbers start at 1 and increase by 1 per case; never reused or renumbered. |
| BR-03 | When a run is created it pins one case version: the approved version if the project enforces approval, otherwise the latest version. Cases with no eligible version are excluded with a warning. |
| BR-04 | "Update to latest version" is allowed only while the run has no result attempt (status Not Run). |
| BR-05 | "Replace run" (run has at least one finalized result) creates a new run at the latest eligible version in the same cycle; the old run is marked superseded, keeps its results, and is excluded from metrics. |
| BR-06 | A result attempt is **draft** while being executed and is editable only by its executor (or a user with `cycle.manage`). Once **finalized** it is immutable. |
| BR-07 | A run has at most one draft attempt at a time. |
| BR-08 | Run status = status of the latest finalized attempt; `in_progress` if a draft attempt exists; `not_run` if no attempt exists. |
| BR-09 | Finalized status of a Steps attempt: Failed if any step Failed; else Blocked if any step Blocked; else Passed if every step is Passed or Skipped and at least one Passed; otherwise the tester must choose Blocked, Skipped or Not Applicable with a reason. A Text attempt's status is chosen by the tester. |
| BR-10 | Blocked, Skipped and Not Applicable as run-level outcomes require a reason. A Failed step requires an actual result. |
| BR-11 | In a Closed cycle no attempts can be started or finalized and assignments cannot change. Reopening requires `cycle.reopen` and a reason. |
| BR-12 | A case appears at most once among the non-superseded runs of a cycle. |
| BR-13 | Archived cases cannot be added to plans or cycles. Deprecated cases cannot be added to new cycles; existing references stay and show a warning. |
| BR-14 | A case can be hard-deleted only if it has never been included in a run, by a user with `testcase.delete`; the deletion is audited. |
| BR-15 | A folder can be deleted only if it contains no cases (including archived) and no subfolders. Folder names are unique among siblings; maximum depth 10. |
| BR-16 | Human-readable keys (`SPARK-TC-123`) are allocated sequentially per project and entity type, never reused, and never change when an item moves. |
| BR-17 | With approval enforced, cycles use the approved version; a newer unapproved version does not affect cycles until approved. |
| BR-18 | With approval enabled, the author of a version cannot approve it unless the project allows self-approval. |
| BR-19 | Defect status changes follow the state machine in the functional spec; each transition requires the corresponding permission. Duplicate requires `duplicate_of`; Rejected and Cannot Reproduce require a resolution note. |
| BR-20 | A defect created from a result is linked to that result, its run, the pinned case version, the failing step and the environment. |
| BR-21 | When a defect moves to Ready for Retest, every non-superseded run linked to it in a non-closed cycle gets `needs_retest = true`; a new finalized attempt on that run clears it. |
| BR-22 | A passing retest never changes defect status automatically; the tester is prompted to verify. |
| BR-23 | Requirement coverage and status are computed per release (functional spec §10.5). |
| BR-24 | Metrics follow the exact definitions in functional spec §11.2. Superseded runs are always excluded; Not Applicable runs are excluded from denominators but shown. |
| BR-25 | Every update to a mutable record carries the `row_version` it read; a mismatch is rejected with HTTP 409. |
| BR-26 | Audit events are written in the same database transaction as the change and are never updated or deleted. |
| BR-27 | Project keys: 2–10 characters, uppercase letters and digits, starting with a letter, unique in the organization, immutable. |
| BR-28 | Attachments on finalized results, approved versions and closed defects cannot be removed. |
| BR-29 | New project members receive the Viewer role unless a role is specified. |
| BR-30 | Executing a run in a Planned cycle moves the cycle to Active. |
| BR-31 | Cycles created from a plan snapshot the plan's case list at that moment; later plan changes affect the cycle only via "Sync from plan", which adds new cases and never removes runs with results. |
| BR-32 | When a run is executed by someone other than its assignee, `executed_by` records the actual user; if the project enables "only assignee executes", others are blocked unless they hold `cycle.manage`. |
| BR-33 | The source of truth for each entity is fixed (HLD §8.3): TCMS owns cases, plans, cycles, results; for Jira-linked projects Jira owns mirrored requirements and Jira-created defects' status. |

## 8. Non-functional requirements

### 8.1 Security — NFR-SEC

| ID | Requirement |
| --- | --- |
| NFR-SEC-01 | Passwords hashed with Argon2id; minimum 12 characters; rejected if in a bundled common-password list. |
| NFR-SEC-02 | Session cookies `HttpOnly`, `Secure`, `SameSite=Lax`; CSRF token required on state-changing requests from the browser. |
| NFR-SEC-03 | Idle timeout default 30 min, absolute 12 h (org-configurable within 15 min–8 h idle, 1–24 h absolute). |
| NFR-SEC-04 | Lockout: 10 failed sign-ins in 15 min locks the account for 15 min; per-IP rate limit on auth endpoints. |
| NFR-SEC-05 | Authorization checked on every request on the server; tenant scoping (organization and project) enforced in the data-access layer. |
| NFR-SEC-06 | Input validated with typed schemas; output encoding; Markdown rendered with sanitization (no raw HTML). |
| NFR-SEC-07 | Uploads: size limit (default 25 MB), allow-listed types verified by content sniffing, stored under random keys, served with `Content-Disposition: attachment` except images/PDF previews, never executed. |
| NFR-SEC-08 | Secrets (TOTP seeds, integration credentials) encrypted at rest with an application key (AES-256-GCM); keys from environment/secret store. |
| NFR-SEC-09 | TLS 1.2+ for all external traffic; HSTS; security headers (CSP, X-Content-Type-Options, frame-ancestors none). |
| NFR-SEC-10 | API tokens stored hashed; shown once; scoped; expiry ≤ 1 year. |
| NFR-SEC-11 | Dependencies scanned in CI; no critical/high known vulnerabilities at release. |
| NFR-SEC-12 | OWASP ASVS Level 2 used as the verification checklist. |

### 8.2 Performance — NFR-PERF (at 10× year-1 data: 100k cases/project, 500k results)

| ID | Requirement |
| --- | --- |
| NFR-PERF-01 | API p95 < 300 ms for list/detail endpoints; p99 < 1 s. |
| NFR-PERF-02 | Repository folder tree with 2,000 folders loads < 1 s. |
| NFR-PERF-03 | Saving a step result < 200 ms p95. |
| NFR-PERF-04 | Dashboards render < 2 s p95. |
| NFR-PERF-05 | Global search returns < 500 ms p95. |
| NFR-PERF-06 | Import of 5,000 cases (20,000 steps) completes < 2 min in the background. |
| NFR-PERF-07 | 50 concurrent testers executing without errors or lost updates. |

### 8.3 Scalability — NFR-SCAL

| ID | Requirement |
| --- | --- |
| NFR-SCAL-01 | Multiple organizations and projects in one deployment with strict data isolation. |
| NFR-SCAL-02 | Stateless API and worker processes; horizontal scaling by adding containers. |
| NFR-SCAL-03 | Attachments in object storage; database holds metadata only. |
| NFR-SCAL-04 | Heavy work (imports, exports, snapshots, sync) in background jobs. |

### 8.4 Reliability — NFR-REL

| ID | Requirement |
| --- | --- |
| NFR-REL-01 | Every business operation runs in a single transaction; partial writes are impossible. |
| NFR-REL-02 | Background jobs retried with exponential backoff (max 5) and dead-lettered with visible error. |
| NFR-REL-03 | Nightly database backup with 30-day retention; documented, tested restore (quarterly). RPO 24 h, RTO 4 h. |
| NFR-REL-04 | Integration failures never block core workflows; failures visible to admins. |
| NFR-REL-05 | Health endpoints for liveness and readiness. |

### 8.5 Usability and accessibility — NFR-UX

| ID | Requirement |
| --- | --- |
| NFR-UX-01 | Execute a step result with keyboard only; at most one click/keystroke per step status. |
| NFR-UX-02 | Common QA tasks (start next run, raise defect from failure, assign 50 runs) complete in ≤ 3 interactions after reaching the screen. |
| NFR-UX-03 | WCAG 2.2 AA. Status never conveyed by colour alone. |
| NFR-UX-04 | Responsive: full function ≥ 1280 px; read and execute ≥ 768 px; read-only dashboards ≥ 375 px. |
| NFR-UX-05 | Supported browsers: current and previous major Chrome, Edge, Firefox, Safari. |

### 8.6 Maintainability and operability — NFR-MNT

| ID | Requirement |
| --- | --- |
| NFR-MNT-01 | Backend line coverage ≥ 85% on domain/service code; every BR has at least one automated test. |
| NFR-MNT-02 | Typed code: mypy (strict on domain/services), TypeScript strict. |
| NFR-MNT-03 | API client for the frontend generated from the OpenAPI schema. |
| NFR-MNT-04 | Structured JSON logs with request ID; no secrets or personal data beyond user ID in logs. |
| NFR-MNT-05 | Single `docker compose up` brings up a working local environment with seed data. |
| NFR-MNT-06 | Database migrations forward-only via Alembic; each migration reviewed and tested. |

### 8.7 Compliance support — NFR-CMP

| ID | Requirement |
| --- | --- |
| NFR-CMP-01 | Audit log retained ≥ 3 years (configurable, never less than 1 year). |
| NFR-CMP-02 | Access-review export (FR-AUD-004). |
| NFR-CMP-03 | Evidence of MFA enforcement per user. |
| NFR-CMP-04 | Data export of an entire project for portability. |

## 9. Scope

**In scope (product):** all FRs above, delivered in the phases in [09 Roadmap](09-Implementation-Roadmap.md).

**MVP = every FR with priority M.** MVP exit gate: a SPARK QA team runs a full regression cycle (≥ 250 cases, ≥ 3 testers, defects raised and retested, readiness decision recorded) entirely in TCMS.

**Out of scope:**
- Billing, plans, self-service signup.
- Native mobile apps (responsive web only).
- Executing automated tests or provisioning environments (TCMS receives results).
- Generating load for performance testing (TCMS stores results only).
- General project management (sprints, tasks, time tracking).
- Real-time co-editing of the same test case (optimistic locking instead).
- Chat, video recording, desktop test runner.
- Folder- or record-level permissions.
- Cross-project case sharing.

## 10. Assumptions

| ID | Assumption | If wrong |
| --- | --- | --- |
| AS-01 | Jira Cloud (not Data Center). | Connector auth/API layer changes; core unaffected. |
| AS-02 | The narrow Jira connector starts Phase 2. | Defect double-entry persists longer. |
| AS-03 | For Jira-linked projects Jira is the source of truth for stories/requirements; TCMS-authored requirements elsewhere. | Requirement ownership rules (BR-33) change. |
| AS-04 | Data-validation case format is Phase 2. | SPARK telemetry tests use Steps format in MVP. |
| AS-05 | Results retained indefinitely; attachment retention configurable, default indefinite. | Add retention jobs earlier. |
| AS-06 | JUnit XML covers SPARK automation frameworks. | Add specific parsers in Phase 2. |
| AS-07 | An SMTP relay is available for invitations, resets and notifications. | Email-less fallback: admins copy invite links. |
| AS-08 | English UI only; UTC storage, user-local display. | Add i18n framework in Phase 3. |
| AS-09 | A single deployment hosts all organizations of the company. | — |

## 11. Dependencies

| ID | Dependency | Needed for |
| --- | --- | --- |
| DEP-01 | PostgreSQL 16+ | All |
| DEP-02 | S3-compatible object storage (MinIO locally) | Attachments, exports |
| DEP-03 | SMTP relay | Invitations, password reset, notifications |
| DEP-04 | Docker host with TLS termination (reverse proxy) | Deployment |
| DEP-05 | Backup storage outside the database host | NFR-REL-03 |
| DEP-06 | Jira Cloud admin to register OAuth app or issue API tokens | Phase 2 |
| DEP-07 | CI system (GitHub Actions/GitLab/Jenkins) able to POST files | Phase 2 automation |

## 12. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| RK-01 | Scope creep into a full ALM | High | High | MoSCoW enforced; out-of-scope list; gate reviews |
| RK-02 | Generated code becomes hard for two developers to maintain | Medium | High | Strict layering, conventions in CLAUDE.md, typed code, high test coverage, ADRs |
| RK-03 | Testers keep using Excel because the runner is slower | Medium | High | Runner performance targets; usability test with SPARK testers before MVP gate |
| RK-04 | Internal defects abandoned in favour of Jira | High | Medium | Jira connector first in Phase 2 |
| RK-05 | Incorrect metrics damage trust | Medium | High | Metric definitions with tests; numerator/denominator shown |
| RK-06 | Data loss or tampering | Low | High | Append-only results and audit, DB-level guards, backups, restore tests |
| RK-07 | Excel import of messy legacy data | High | Medium | Dry run with row-level errors, mapping UI, re-runnable import |
| RK-08 | Tenant data leak via missing scope filter | Low | High | Scoped repository base class, automated cross-tenant tests on every endpoint |
| RK-09 | Performance degradation with large histories | Medium | Medium | Indexes, summary tables, performance tests at 10× data |

## 13. Product-level acceptance criteria (MVP)

| ID | Criterion |
| --- | --- |
| AC-PRD-01 | All M-priority FRs implemented with their functional-spec acceptance criteria passing. |
| AC-PRD-02 | Every BR covered by at least one automated test that fails if the rule is broken. |
| AC-PRD-03 | No path in the API or UI can modify a finalized result or an audit event (verified by tests and DB guards). |
| AC-PRD-04 | Cross-tenant access tests pass for every endpoint. |
| AC-PRD-05 | NFR-PERF targets met in the performance test at 10× year-1 data. |
| AC-PRD-06 | OWASP ZAP baseline scan: no high findings; ASVS L2 checklist reviewed. |
| AC-PRD-07 | SPARK pilot: full regression cycle completed in TCMS; ≥ 80% of pilot testers rate execution "as fast or faster" than their previous method. |
| AC-PRD-08 | Backup restore rehearsed successfully. |
| AC-PRD-09 | Fresh `docker compose up` produces a working seeded system in < 10 minutes on a developer laptop. |
