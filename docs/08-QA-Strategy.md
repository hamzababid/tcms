# 08 — QA Strategy for the TCMS Application

| Field | Value |
| --- | --- |
| Version | 1.0 · 2026-11-03 |
| Depends on | [01 PRD](01-PRD.md), [02 Functional Spec](02-Functional-Specification.md), [04 LLD](04-LLD.md) |

A test management tool that loses or misreports results is worse than none. This strategy concentrates effort on the rules that make results trustworthy: immutability, roll-up, coverage, metrics, authorization and tenant isolation.

---

## 1. Objectives

1. Every business rule (BR-01…BR-33) and every acceptance criterion (`AC-*`) has an automated test that fails when the rule is broken.
2. No API path can modify finalized results or audit events (proved by tests at API and database level).
3. No cross-tenant or cross-project data exposure (tested for every endpoint).
4. Metrics and coverage match a reference implementation on generated data.
5. Performance targets (NFR-PERF) hold at 10× year-1 data.
6. Testers in the SPARK pilot can execute faster than with their current method (AC-PRD-07).

## 2. Test levels and tooling

| Level | Scope | Tools | Runs | Owner |
| --- | --- | --- | --- | --- |
| Unit | Pure rules: roll-up, transitions, coverage status, metric formulas, content normalization, key formatting, permissions resolution, readiness evaluation | pytest, Hypothesis (property tests); Vitest for frontend utilities | Every commit | Developers (Claude Code) |
| Integration (service + DB) | Service functions with real PostgreSQL: transactions, triggers, constraints, audit writes, scoping | pytest + testcontainers PostgreSQL 16, factory_boy | Every commit | Developers |
| API | HTTP behaviour per endpoint: status codes, schemas, errors, permissions, pagination/filter/sort | pytest + httpx TestClient | Every commit | Developers |
| Contract / fuzz | OpenAPI conformance and robustness | Schemathesis (stateful links) | Every merge to main | Developers |
| Frontend component | Components (DataTable, StepGrid, StepRunner, StatusBadge, Metric, FolderTree), hooks | Vitest + Testing Library, MSW | Every commit | Developers |
| End-to-end | Critical user journeys in a browser against compose stack | Playwright (Chromium, Firefox, WebKit nightly) | Every merge (Chromium); nightly (all) | QA |
| Accessibility | Automated axe checks on every E2E page + manual keyboard/screen-reader passes per milestone | @axe-core/playwright, NVDA/VoiceOver | Every merge (axe); per milestone (manual) | QA |
| Performance | Load and soak at 10× data | k6, seed-large | Nightly on staging; before each release | QA |
| Security | SAST, dependency scan, DAST, authz matrix, manual review against ASVS L2 | ruff security rules (bandit set), pip-audit, npm audit, Trivy, OWASP ZAP baseline + authenticated scan | Every commit (SAST/deps); nightly (ZAP); pre-release (manual) | QA + developers |
| Migration | Upgrade from previous release DB; schema drift check | Alembic, pytest | Every merge | Developers |
| Backup/restore | Restore drill | ops scripts | Quarterly + before MVP go-live | Ops |
| UAT | SPARK pilot | TCMS itself (dogfooding) + survey | Milestone M9 | QA Manager |

Target pyramid (by count): ~60% unit, ~25% integration/API, ~10% component, ~5% E2E.

## 3. Environments and test data

| Environment | Data | Notes |
| --- | --- | --- |
| Unit/integration | Factories per test; transactional rollback per test (savepoints) except tests of transaction behaviour | Fresh container per worker (`pytest-xdist`) |
| E2E (CI) | `tcms seed --profile e2e`: 1 org, 2 projects (SPARK, HELIOS), one user per role per project, 300 cases, 2 releases, cycles in each status | Deterministic IDs and passwords |
| Staging | `tcms seed --profile large`: 3 orgs; SPARK with 100,000 cases, 2,000 folders, 50 releases, 2,000 cycles, 500,000 attempts, 20,000 defects, 5,000 requirements | Used for perf and manual exploration |
| UAT | Real SPARK import into staging (anonymized users) | Pilot |

Rules: tests never depend on wall-clock time (frozen clock fixture), on order, or on shared state. Test users and passwords are fixtures, never real data.

## 4. CI quality gates

```
lint+types ─► unit ─► integration+API ─► contract ─► build images ─► e2e (chromium) + axe ─► merge
                                                                     │
nightly: e2e all browsers · ZAP · perf (staging) · dependency audit · restore smoke test
```

| Gate | Threshold |
| --- | --- |
| Lint/type | ruff, mypy (strict on `rules`, `service`), ESLint, `tsc --noEmit`, import-linter contracts: zero errors |
| Unit + integration + API | 100% pass; coverage ≥ 85% lines on `*/service.py`, `*/rules.py`, `reporting/*`; ≥ 95% branches on `*/rules.py` |
| BR traceability | `tests/test_rule_coverage.py` asserts that every BR of a completed milestone (manifest `tests/br_manifest.py`) appears in at least one test name or marker; BR-33 is Phase 2 |
| OpenAPI drift | Generated client equals committed client |
| Migrations | `alembic upgrade head` from empty and from previous release; `alembic check` clean |
| E2E | 100% pass; flaky tests quarantined with ticket, max 3 quarantined |
| Security | No critical/high in pip-audit/npm audit/Trivy (or documented exception with expiry) |
| Accessibility | No serious/critical axe violations |

## 5. Functional testing approach by module

| Module | Focus | Main techniques |
| --- | --- | --- |
| AUTH | Login, MFA, lockout, reset, invitations, sessions, tokens | State transitions, negative tests, timing-equality check for user enumeration |
| WS | Project keys, settings effects, archive read-only | Boundary values (key format), decision tables (settings) |
| TD | Versioning, review workflow, archive/deprecate/delete rules, folders | State-transition testing of case status; equivalence classes for content vs metadata changes |
| PLN | Selection rules, exclusions, cycle generation, sync | Decision tables for eligibility |
| EXE | Attempts, roll-up, retest/correction, version update/replace, close/reopen, concurrency | Exhaustive roll-up matrix (§6.1), concurrency tests (§10) |
| DEF | State machine, permissions per transition, prefill, retest flags | Full transition matrix 13×13 × permission sets |
| REQ | Coverage status rules, scope rules | Reference implementation comparison (property tests) |
| RPT | Metric formulas, undefined denominators, filters | Reference implementation, golden datasets |
| IMP | Mapping, row models, validation, all-or-nothing | Golden files (valid, messy, malicious), round-trip export→import |
| AUD | Event presence for every action, immutability | Parameterized "every mutating endpoint writes audit" test |
| SRCH | Key lookup, fuzzy match, scoping | Example-based |

## 6. Business-rule test design

### 6.1 Roll-up matrix (BR-09) — unit, exhaustive

Generate all combinations of step statuses for 1–4 steps (5⁴ + … = 780 cases) × explicit outcome ∈ {none, blocked, skipped, not_applicable, passed, failed} and compare `compute_final_status` with a table-driven oracle written independently from the specification table in [02 §7.3](02-Functional-Specification.md). Plus property tests:

- If any step failed, result is failed or the call raises `outcome_conflicts_with_steps`.
- Explicit `passed` is never accepted for step-format attempts.
- A passed result never contains a `not_run`, `failed` or `blocked` step.

### 6.2 Defect transitions (BR-19)

Matrix test: for each (from, to) of 13×13 and each permission profile {any, dev-as-assignee, dev-not-assignee, verify, none} assert allowed/denied exactly as the table; for allowed ones, assert required-field validation.

### 6.3 Coverage (BR-23)

Hypothesis generates projects with random requirements, links, cases (some archived), cycles in/out of the release, runs (some superseded) and attempts (statuses, times, NA). Compare SQL implementation output with a pure-Python oracle implementing [02 §10.5](02-Functional-Specification.md) literally.

### 6.4 Metrics (BR-24)

Same generator; compare `ExecutionSummary` from SQL with an oracle; assert `None` for zero denominators; assert superseded runs excluded.

### 6.5 BR → test mapping (minimum)

| BR | Test(s) |
| --- | --- |
| BR-01/02 | `test_br_01_content_change_creates_version`, `test_br_01_metadata_change_no_version`, `test_br_02_version_numbers_sequential_under_concurrency` |
| BR-03/17 | `test_br_03_run_pins_approved_version_when_enforced`, `test_br_03_run_pins_latest_when_not_enforced`, `test_br_03_excludes_without_eligible_version` |
| BR-04/05 | `test_br_04_update_version_only_without_attempts`, `test_br_05_replace_run_supersedes_and_excludes_from_metrics` |
| BR-06/07 | `test_br_06_final_result_immutable_api`, `test_br_06_final_result_immutable_sql`, `test_br_07_single_draft_per_run` |
| BR-08/09/10 | Roll-up matrix (§6.1), `test_br_10_reason_required` |
| BR-11 | `test_br_11_closed_cycle_rejects_attempts`, `test_br_11_reopen_requires_reason_and_permission` |
| BR-12 | `test_br_12_case_once_per_cycle` |
| BR-13/14/15 | `test_br_13_archived_not_selectable`, `test_br_14_delete_only_never_run`, `test_br_15_folder_delete_only_empty` |
| BR-16/27 | `test_br_16_keys_never_reused_after_delete`, `test_br_27_project_key_format` |
| BR-18 | `test_br_18_self_approval_blocked` |
| BR-19 | Transition matrix (§6.2) |
| BR-20/21/22 | `test_br_20_defect_from_result_links`, `test_br_21_ready_for_retest_flags_runs`, `test_br_22_retest_pass_does_not_change_defect` |
| BR-23/24 | Property tests (§6.3, §6.4) |
| BR-25 | `test_br_25_stale_row_version_409` (per mutable resource, parameterized) |
| BR-26 | `test_br_26_audit_in_same_transaction` (rollback leaves no audit), `test_br_26_audit_append_only_sql` |
| BR-28 | `test_br_28_attachment_on_final_result_not_removable` |
| BR-29 | `test_br_29_new_member_default_viewer` |
| BR-30/31/32 | `test_br_30_first_execution_activates_cycle`, `test_br_31_sync_from_plan_adds_only`, `test_br_32_only_assignee_setting` |
| BR-33 | (P2) connector tests |

## 7. Authorization and tenant-isolation testing

- **Authorization matrix:** a table in `tests/api/authz_matrix.py` lists every endpoint with its required permission. A parameterized test calls each endpoint as each role (+ non-member + other-org user + API token read scope) and asserts 2xx/403/404 as expected. A guard test fails if any route in the FastAPI app is missing from the matrix.
- **Cross-tenant:** fixture with two orgs having identical project keys; for each GET/PATCH/DELETE by ID, use IDs from the other org → expect 404; list endpoints never include foreign rows.
- **Resource rules:** draft executor-only, dev-only-if-assignee, self-approval, only-assignee-executes.

## 8. Security testing

| Area | Tests |
| --- | --- |
| Authentication | Lockout, rate limits, enumeration timing, reset-token reuse/expiry, session fixation (new session ID after login), logout revokes, idle/absolute expiry, MFA replay protection, recovery code single use |
| Session/CSRF | State-changing request without CSRF header → 403; SameSite cookie flags; bearer requests ignore cookies |
| Input handling | SQL injection payloads on all filter/sort/q params (Schemathesis + custom); XSS payloads in every Markdown field rendered in UI (Playwright asserts no script execution); CSV formula injection in exports; path traversal in file names |
| Uploads | Oversize (413), spoofed MIME (exe renamed .png → 415), polyglot files, zip bombs not extracted, SVG rejected (not in allow-list), download headers |
| XML (P2) | XXE and billion-laughs payloads to JUnit import |
| Headers/TLS | CSP, HSTS, frame-ancestors, nosniff present; TLS config via testssl.sh on staging |
| Secrets | TOTP secrets and integration credentials encrypted at rest (DB inspection test) |
| DAST | ZAP baseline nightly; authenticated full scan before each release |
| Manual | ASVS L2 checklist review before MVP go-live; threat-model review per module PR touching auth or permissions |

## 9. Performance testing

Data: staging `large` profile (§3). Tool: k6. Targets from NFR-PERF.

| Scenario | Load | Pass criteria |
| --- | --- | --- |
| P1 Browse repository | 30 VUs: tree, list folder, open case, search | p95 < 300 ms API; tree < 1 s |
| P2 Execution | 50 VUs each executing runs: start, 10 step PATCHes (2 s think time), finalize | p95 step save < 200 ms; 0 errors; no lost updates (post-check counts) |
| P3 Dashboards | 10 VUs: manager dashboard, quality dashboard, traceability for a 5,000-requirement release | p95 < 2 s |
| P4 Mixed soak | 50 VUs mixed P1–P3 for 2 h | No memory growth > 10%; error rate < 0.1% |
| P5 Background | Import 5,000 cases / 20,000 steps; export 100,000 runs | Import < 2 min; export completes; API p95 unaffected (< +20%) |
| P6 Cycle creation | Create cycle with 5,000 runs | Job completes < 60 s |

Each release records results in a performance log; regressions > 20% block release.

## 10. Data integrity testing

| Test | Method |
| --- | --- |
| Final results immutable | Attempt UPDATE/DELETE via SQL as `tcms_app` on final results/step results → exception; via every API path → 409/422 |
| Versions immutable | SQL UPDATE of content columns → exception; approval columns settable once |
| Audit append-only | SQL UPDATE/DELETE as app role → permission error |
| Atomicity | Fault injection (raise after first insert) in finalize, import commit, cycle creation → no partial data, no audit rows |
| Concurrency | 20 threads finalize the same draft → exactly one succeeds; 20 threads start attempts on the same run → one draft; 10 threads save new versions of the same case → sequential version numbers, no gaps from committed ones; concurrent `row_version` edits → one 409 per loser |
| Consistency job | Nightly `execution.verify_run_status` on staging must report 0 mismatches |
| Migration safety | Upgrade previous-release seeded DB; compare row counts and checksums of immutable tables before/after |
| Backup/restore | Restore last night's dump to a clean instance; run smoke suite and integrity queries |

## 11. Regression strategy

- The full automated suite is the regression suite; it runs on every merge.
- E2E smoke subset (tag `@smoke`, ~15 tests, < 5 min) runs on every deploy to staging and production.
- Dogfooding: from milestone M6 the TCMS team manages its own manual regression (UI checks not automated) **in TCMS**, with a "TCMS Regression" plan; each release runs a cycle and records a go/no-go decision.
- Every production bug gets a regression test before the fix merges.

## 12. User acceptance testing (SPARK pilot, milestone M9)

| Item | Plan |
| --- | --- |
| Participants | QA Manager, QA Lead, 3–5 QA Engineers, 2 Developers, 1 PM |
| Duration | 2 weeks (one full regression cycle + defect lifecycle) |
| Scenarios | UJ-1 … UJ-9 from [01 PRD §5](01-PRD.md) with real SPARK data imported |
| Measures | Time to execute 20 cases vs previous method (same testers); defects with complete reproduction info (developer rating); SUS questionnaire (target ≥ 75); count of blocking issues |
| Exit | No open critical/high TCMS defects; AC-PRD-07 met; QA Manager sign-off recorded as a release decision in TCMS |

## 13. Defect management for TCMS itself

TCMS defects are tracked in TCMS (project `TCMS`) once M6 is reached; before that in the repository's issue tracker. Severity definitions:

| Severity | Definition |
| --- | --- |
| Critical | Data loss/corruption, security breach, wrong results/metrics shown as correct, system unusable |
| High | Core workflow blocked without workaround (execution, case editing, defect creation) |
| Medium | Workflow impaired with workaround; incorrect non-critical display |
| Low | Cosmetic, minor usability |

Release blocking: any open Critical or High.

## 14. Entry and exit criteria

| Milestone/release | Entry | Exit |
| --- | --- | --- |
| Each milestone | Scope stories have AC; designs for UI stories reviewed | All milestone stories' AC tests pass; CI gates green; no open critical/high; docs updated |
| MVP release | M0–M9 complete | AC-PRD-01…09 met; performance log within targets; ZAP authenticated scan clean of high; ASVS L2 review done; restore drill done; UAT sign-off |
| Phase 2 releases | Phase gate (Jira/CI) defined | Connector tests with Jira Cloud sandbox; ingestion tests with JUnit samples from Playwright, pytest, JUnit5, Cypress, Newman |

## 15. Initial test case catalog

Level: **U** unit, **I** integration, **A** API, **E** end-to-end, **P** performance, **S** security. Priority: H/M/L. These are the first cases to implement; each maps to requirements and ACs. They are also imported into TCMS as the seed of the "TCMS Regression" plan (`docs/seed/tcms-regression.csv` generated from this table).

### 15.1 Authentication and access

| ID | Title | Lvl | Pri | Refs | Expected |
| --- | --- | --- | --- | --- | --- |
| TCMS-001 | Sign in with valid credentials (no MFA) | E | H | FR-AUTH-001, AC-AUTH-01 | Lands on the last project (or the project list) until My Work exists in M4; secure cookie set |
| TCMS-002 | Unknown email and wrong password give identical responses | A | H | AC-AUTH-02 | Same status/body; timing within 50 ms average |
| TCMS-003 | Account locks after 10 failures | A | H | FR-AUTH-007, AC-AUTH-03 | 11th attempt refused; `auth.locked` audit |
| TCMS-004 | Org Admin forced to enrol MFA | E | H | FR-AUTH-002, AC-AUTH-04 | Only MFA enrolment accessible until done |
| TCMS-005 | TOTP enrolment and sign-in with code | E | H | FR-AUTH-002 | Codes accepted; replay of same code rejected |
| TCMS-006 | Recovery code works once | A | H | AC-AUTH-05 | Second use rejected |
| TCMS-007 | Password reset link single use and expires | A | H | FR-AUTH-004 | Reuse/expired → error; sessions revoked |
| TCMS-008 | Invitation acceptance creates active member with role | E | H | FR-AUTH-005 | User in project with invited role |
| TCMS-009 | Idle session expires | A | M | AC-AUTH-06 | 401 session_expired |
| TCMS-010 | API token with read scope cannot write | A | H | FR-AUTH-010 | 403 token_scope_insufficient |
| TCMS-011 | Deactivated user's sessions and tokens revoked | A | H | §3.5 | Subsequent calls 401 |
| TCMS-012 | Authorization matrix for all endpoints | A | H | FR-AUTH-008 | All expectations met |
| TCMS-013 | Cross-tenant access returns 404 | A | H | NFR-SEC-05 | No foreign data |
| TCMS-014 | CSRF header required for cookie writes | S | H | NFR-SEC-02 | 403 without header |

### 15.2 Workspace

| ID | Title | Lvl | Pri | Refs | Expected |
| --- | --- | --- | --- | --- | --- |
| TCMS-020 | Create project with valid key | E | H | FR-WS-002 | Project created; creator QA Manager; default environments |
| TCMS-021 | Project key validation and uniqueness | A | H | BR-27, AC-WS-01 | Invalid → 422; duplicate → 409 |
| TCMS-022 | Archived project is read-only | A | M | AC-WS-02 | Writes → 409 project_archived |
| TCMS-023 | New member defaults to Viewer | A | M | BR-29 | Role viewer |
| TCMS-024 | Release status transitions | A | M | FR-WS-006 | Invalid transitions rejected |
| TCMS-025a | Archived environment hidden from pickers, restorable | A | M | AC-WS-03 | Excluded unless `include_archived` (M1) |
| TCMS-025b | Archived environment not selectable for new cycle | A | M | AC-WS-03 | 422 (M3) |

### 15.3 Repository and test cases

| ID | Title | Lvl | Pri | Refs | Expected |
| --- | --- | --- | --- | --- | --- |
| TCMS-030 | Create nested folders and move a folder | E | H | FR-TD-001 | Tree updated; counts correct |
| TCMS-031 | Prevent folder cycle and depth > 10 | A | M | AC-TD-01/02 | 422 errors |
| TCMS-032 | Delete folder only when empty | A | M | BR-15, AC-TD-03 | 409 when not empty |
| TCMS-033 | Create steps-format case | E | H | FR-TD-002 | v1 created; key allocated |
| TCMS-034 | Content edit creates new version; metadata edit does not | I | H | BR-01, AC-TD-10/11 | Versions as expected; audit events |
| TCMS-035 | Identical save creates no version | A | M | AC-TD-13 | version_created false |
| TCMS-036 | Compare two versions | E | M | FR-TD-004, AC-TD-12 | Diff displays changes |
| TCMS-037 | Restore earlier version | A | M | FR-TD-005 | New version with restored content |
| TCMS-038 | Approval workflow submit/approve/return | E | H | FR-TD-006, AC-TD-20/22 | Statuses and notifications correct |
| TCMS-039 | Self-approval blocked | A | H | BR-18, AC-TD-21 | 403 |
| TCMS-040 | Enabling approval grandfathers existing cases | I | M | §5.4 | All approved at latest |
| TCMS-041 | Deprecate/archive/restore behaviour in pickers | A | M | BR-13 | Excluded appropriately |
| TCMS-042 | Hard delete only never-run case | A | M | BR-14 | 409 case_has_runs otherwise |
| TCMS-043 | Bulk move 300 cases runs as job with per-case audit | I | M | FR-TD-010 | 202, completes, 300 audit events with bulk id |
| TCMS-044 | Duplicate case | A | L | FR-TD-009 | New key, v1, link duplicated_from |
| TCMS-045 | Step attachments carried to new version | I | M | §5.3 | Attachment linked on new step |
| TCMS-046 | Keyboard authoring of 10 steps | E | M | NFR-UX-01 | Steps created without mouse |
| TCMS-047 | Concurrent edit returns conflict dialog | E | M | BR-25 | Conflict dialog shown |

### 15.4 Plans and cycles

| ID | Title | Lvl | Pri | Refs | Expected |
| --- | --- | --- | --- | --- | --- |
| TCMS-050 | Create plan with exit rules and risks | E | H | FR-PLN-001 | Saved; rules evaluable |
| TCMS-051 | Add cases by folder/tag with exclusions report | A | H | FR-PLN-002 | Added/skipped counts correct |
| TCMS-052 | Create cycle from plan skipping ineligible | A | H | AC-PLN-01 | 195 runs, 5 skipped |
| TCMS-053 | Sync from plan adds only new | A | M | BR-31, AC-PLN-02 | Runs added, none removed |
| TCMS-054 | Cycle with 5,000 cases created in background | I | M | §7.1 | runs_pending then complete |
| TCMS-055 | Bulk assign by folder | E | H | FR-EXE-004 | Assignees set; notifications |
| TCMS-056 | Claim pool run | A | M | FR-EXE-004 | Assigned to claimer |
| TCMS-057 | Remove run with results refused | A | M | §7.1 | 409 run_has_results |
| TCMS-058 | Close cycle with drafts prompts | E | M | FR-EXE-012 | Drafts listed; discard option |
| TCMS-059 | Reopen requires permission and reason | A | M | BR-11 | 403 / 422 / success |
| TCMS-060 | Clone cycle with only failed/blocked/not run | A | M | §7.1 | Correct subset at current versions |

### 15.5 Execution

| ID | Title | Lvl | Pri | Refs | Expected |
| --- | --- | --- | --- | --- | --- |
| TCMS-070 | Execute run all passed | E | H | FR-EXE-005/006 | Run passed; cycle progress updated |
| TCMS-071 | Roll-up matrix | U | H | BR-09 | All combinations correct |
| TCMS-072 | Failed step requires actual result | A | H | BR-10 | 422 actual_result_required |
| TCMS-073 | Incomplete attempt cannot finish without outcome | A | H | AC-EXE-03 | 422 incomplete_attempt |
| TCMS-074 | Block run with reason | E | H | FR-EXE-008 | Status blocked; reason shown |
| TCMS-075 | Passed with skipped steps flagged | A | M | AC-EXE-02 | skipped_steps = 1 |
| TCMS-076 | Final result immutable (API + SQL) | I | H | BR-06, AC-EXE-04 | Rejected |
| TCMS-077 | Single draft per run; take-over by manager | A | H | BR-07, AC-EXE-05 | 409; take-over audited |
| TCMS-078 | Closed cycle rejects execution | A | H | AC-EXE-06 | 409 cycle_closed |
| TCMS-079 | Retest adds attempt and updates status | E | H | FR-EXE-009, AC-EXE-07 | History shows both |
| TCMS-080 | Correct result with reason | A | M | FR-EXE-010 | New attempt references corrected |
| TCMS-081 | Pinned version shown after case edit | E | H | BR-03, AC-EXE-08 | Old steps displayed |
| TCMS-082 | Update to latest only without attempts | A | H | BR-04 | Allowed/denied correctly |
| TCMS-083 | Replace run supersedes and excludes from metrics | A | H | BR-05 | Old superseded; summary excludes |
| TCMS-084 | First execution activates planned cycle | A | M | BR-30 | Cycle active |
| TCMS-085 | Only-assignee setting enforced | A | M | BR-32 | 403 not_assignee for others |
| TCMS-086 | Runner keyboard flow and auto-advance | E | H | NFR-UX-01 | Run completed with keyboard only |
| TCMS-087 | Paste screenshot into actual result | E | M | §7.4 | Attachment saved and shown |
| TCMS-088 | Save failure retry indicator | E | M | §7.4 | "Not saved" shown; recovers |
| TCMS-089 | Text-format case execution | E | M | §7.3 | Tester-selected status |
| TCMS-090 | Concurrent finalize of same draft | I | H | §10 | Exactly one succeeds |

### 15.6 Defects

| ID | Title | Lvl | Pri | Refs | Expected |
| --- | --- | --- | --- | --- | --- |
| TCMS-100 | Raise defect from failed step prefilled | E | H | FR-DEF-002, AC-DEF-02 | Fields and links prefilled |
| TCMS-101 | Transition matrix with permissions | U/A | H | BR-19, AC-DEF-01 | As table |
| TCMS-102 | Duplicate requires duplicate_of | A | M | AC-DEF-04 | 422 |
| TCMS-103 | Ready for retest flags linked runs | I | H | BR-21, AC-DEF-03 | needs_retest true |
| TCMS-104 | Passing retest prompts verify, no auto change | E | H | BR-22 | Defect unchanged until confirmed |
| TCMS-105 | Link existing defect to another result | A | M | FR-DEF-003 | Link created |
| TCMS-106 | Defect status history recorded | I | M | FR-DEF-005 | History rows per transition |
| TCMS-107 | Bulk transition only valid transitions | A | M | FR-DEF-006 | Invalid rejected per item |

### 15.7 Requirements, reporting, search

| ID | Title | Lvl | Pri | Refs | Expected |
| --- | --- | --- | --- | --- | --- |
| TCMS-110 | Link requirements and cases many-to-many | A | H | FR-REQ-002 | Links visible both sides |
| TCMS-111 | Coverage status rules | U/I | H | BR-23, AC-REQ-01..04 | Matches oracle |
| TCMS-112 | RTM for release shows uncovered | E | H | FR-REQ-004 | Filters correct |
| TCMS-113 | Execution summary rates and undefined denominators | U/A | H | BR-24 | Matches oracle; null for 0 |
| TCMS-114 | Superseded runs excluded from metrics | A | H | BR-24 | Counts exclude |
| TCMS-115 | Manager dashboard widgets consistent with reports | E | M | FR-RPT-001 | Same numbers |
| TCMS-116 | Readiness rules evaluate and decision stored immutable | A | H | FR-RPT-006 | Snapshot stored; append-only |
| TCMS-117 | Export cycle report XLSX with formula-injection protection | A | M | FR-RPT-005, A03 | Cells prefixed |
| TCMS-118 | Global search by exact key | E | M | FR-SRCH-001 | Jumps to item |
| TCMS-119 | Fuzzy title search within project only | A | M | FR-SRCH-001 | Scoped results |
| TCMS-120 | Saved view shared within project | E | L | FR-SRCH-003 | Visible to members |

### 15.8 Audit, import/export, platform

| ID | Title | Lvl | Pri | Refs | Expected |
| --- | --- | --- | --- | --- | --- |
| TCMS-130 | Every mutating endpoint writes an audit event | A | H | FR-AUD-001 | Parameterized pass |
| TCMS-131 | Audit append-only at DB level | I | H | BR-26 | Permission error |
| TCMS-132 | Rolled-back operation leaves no audit | I | H | BR-26 | 0 audit rows |
| TCMS-133 | Access review export contents | A | H | FR-AUD-004 | All users × scopes, MFA, last login |
| TCMS-134 | Import dry run reports row errors | E | H | FR-IMP-001, AC-IMP-01 | Errors with rows; commit gated |
| TCMS-135 | Export → re-import unchanged is no-op | A | H | AC-IMP-02 | 0 created/versioned |
| TCMS-136 | Import failure is all-or-nothing | I | H | AC-IMP-03 | No partial data |
| TCMS-137 | Upload type and size enforcement | S | H | NFR-SEC-07 | 413/415 |
| TCMS-138 | Markdown XSS payloads neutralized | S | H | NFR-SEC-06 | No script execution |
| TCMS-139 | Job retry and dead-letter visible to admin | I | M | NFR-REL-02 | Dead job listed; retry works |
| TCMS-140 | Health ready fails when DB down | A | M | NFR-REL-05 | 503 |
| TCMS-141 | Backup restore drill | P | H | NFR-REL-03 | Restored system passes smoke |
| TCMS-142 | Performance scenarios P1–P6 | P | H | NFR-PERF | Targets met |
| TCMS-143 | Accessibility: keyboard-only regression of runner and repository | E | M | NFR-UX-03 | All actions reachable |
