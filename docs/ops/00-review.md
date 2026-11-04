# 00 — Step 0 Review (pre-implementation)

| Field | Value |
| --- | --- |
| Date | 2026-11-04 |
| Scope | Whole specification package (`CLAUDE.md`, `README.md`, `docs/01`–`12`, `docs/schema/*.sql`, `docs/design/*`) |
| Status | **Awaiting maintainer approval.** No application code has been written. |

**What I did:** I read every document in the order `CLAUDE.md` gives. I also applied `00_roles.sql`, `01_baseline.sql` and `02_seed_system.sql` to a throwaway `postgres:16` (16.15) container and ran `99_verify.sql` as `tcms_app`: **35/35 PASS**. I then ran two probes against that database to confirm conflicts K1 and G7 (results quoted below). The container has been removed.

**How to read this:** §1 lists conflicts between documents, with both passages quoted, a proposed fix and the document to change. §2 lists new gaps; README open items are not repeated. §3 is the plan. §4 is the environment check. **§5 collects every decision I need from you, each with my recommended default.** Items marked *(my call)* fall within the LLD's remit ("code structure → LLD wins"). I will apply them as proposed unless you object.

---

## 1. Conflicts between documents

Severity: **B** = blocks M0/M1 · **L** = affects a later milestone (needs a decision before that milestone, not now) · **m** = minor wording/prose fix.

### K1 · `admin_access` audit action violates the schema; and GETs cannot write it — **B (M1)**

- 02 §3.2: "Org Admin … is treated as holding every project permission in every project of the organization (each project access audited as `admin_access`)." 02 §13.1 lists `admin_access` among actions.
- `01_baseline.sql`: `action text NOT NULL CHECK (action ~ '^[a-z_]+\.[a-z_]+$')`. Verified: inserting `admin_access` fails with `violates check constraint "audit_events_action_check"`.
- 04 LLD §3.1: "GET routes use a read-only session (`SET TRANSACTION READ ONLY`)". Most "project access" is a GET, which cannot insert an audit row in that transaction.
- **Proposed fix:** rename the action to `project.admin_accessed` and define "access" as **the first request by a non-member Org Admin to a project per session**. Record it in a separate short write transaction (see G2). Change **02 §3.2, §13.1**. Storage wins on the action format. The frequency is a behaviour choice → **Q1**.

### K2 · Roll-up "Blocked" without a reason is rejected by the database — **L (M4)**

- 02 §7.3 precedence table: "No failed, any blocked | none | blocked" (no reason implied). 01 BR-10: "Blocked, Skipped and Not Applicable **as run-level outcomes** require a reason."
- `01_baseline.sql` `test_results`: `CHECK (state = 'draft' OR status NOT IN ('blocked','skipped','not_applicable') OR coalesce(char_length(reason), 0) > 0 OR source = 'automation') -- BR-10`. `99_verify.sql` asserts it ("BR-10 final blocked result requires a reason").
- **Proposed fix:** storage wins, so **every** final `blocked`/`skipped`/`not_applicable` attempt needs a reason, including a `blocked` derived from steps. The finalize API returns `422 reason_required` and the runner asks for the reason. Change **02 §7.3** (table and prose) and **01 BR-10** wording. → **Q2** (can be confirmed before M4).

### K3 · M1 acceptance includes a test that needs cycles (M3) — **B (M1)**

- 09 M1 Acceptance: "TCMS-001…014, 020…025 pass".
- 08 TCMS-025: "Archived environment not selectable for new cycle | A | … | AC-WS-03 | 422". Cycle creation is M3 (09 M3).
- **Proposed fix:** in M1, TCMS-025 covers the environment part: archiving works, archived environments are excluded from active lists and pickers, and the archive is audited. The "422 on cycle create" assertion moves to M3 acceptance. Change **09 M1/M3**, and split **08 TCMS-025** into TCMS-025a/b.

### K4 · M1 acceptance needs user deactivation, which the backlog puts in M8 — **B (M1)**

- 09 M1 Acceptance includes TCMS-011 "Deactivated user's sessions and tokens revoked". 09 M1 scope covers only "E15 (audit write + record history only)", and the kickoff names "US-010…US-029 and US-160".
- 10 Backlog: US-164 "I manage users (deactivate, reset MFA, revoke sessions, admin flag)" sits in E15 "M1 (core), M8 (UI)".
- **Proposed fix:** build the **backend** of US-164 in M1: deactivate, reactivate, revoke sessions, reset MFA, admin flag, last-admin protection. Its UI stays in M8. Also build the backend of US-161 (record history endpoint), which 09 M1 scope lists as "record history". Change **09 M1 scope**.

### K5 · Post-login landing page does not exist until M4 — **B (M1)**

- 08 TCMS-001: "Sign in with valid credentials (no MFA) | E | … | Lands on My Work". 02 §3.3 step 7: "redirect to last project or My Work".
- 09: My Work is M4 scope; the project overview dashboard is M7 (E13).
- Kickoff non-negotiable: "No dummy buttons or non-functional UI."
- **Proposed fix:** until M4, sign-in lands on the **last project's Activity page** (US-028, built in M1). With no projects, it lands on a real **Projects** list: the user's projects plus "Create project" when they hold `project.create`. Sidebar items appear only when their feature is merged. Change **08 TCMS-001** (expected landing "last project or project list until M4"). → **Q3**

### K6 · "Users can be invited" in M1, but admin screens are M8 — **B (M1)**

- 09 M1 Deliverables: "Users can be invited, sign in with MFA, create SPARK, add members". The M1 frontend scope is "auth screens, shell with project switcher, project settings pages, profile/tokens".
- 09 M8 scope: "admin screens (users, invitations, security policy, audit log, access review, system status/jobs)".
- **Options:** (a) build a minimal Administration › **Invitations** page (list, invite, revoke, copy link) and **Security policy** page (US-021) in M1, and the rest of Admin in M8; (b) M1 invitations via API and `tcms` CLI only. I recommend (a). → **Q4**

### K7 · First-time setup: a QA Manager cannot create the first project — **m (M1)**

- 02 §14 W1 step 4: "QA Manager creates project SPARK …".
- 02 §3.2: "`project.create` … is granted to Org Admin and … to any user who holds QA Manager in at least one project."
- On a fresh organization nobody is QA Manager yet. **Proposed fix:** W1 step 4 becomes "Org Admin creates SPARK (becoming its QA Manager) and invites Ayesha as QA Manager of SPARK". Change **02 §14 W1**. No behaviour change.

### K8 · Seed admin has "MFA off", but admins must use MFA — **B (M1 seed and E2E)**

- 04 LLD §2: `make seed` → "users per role (password `Passw0rd!Passw0rd`, MFA off)".
- 01 FR-AUTH-002: "MFA is always required for Organization Administrators." AC-AUTH-04 makes every call except enrolment return `403`.
- **Options:** (a) the seed admin is pre-enrolled with a **documented, dev-only TOTP secret**. It is written in `docs/ops/local-setup.md` like the seed password, refused when `TCMS_ENV=production`, and E2E computes codes from it. (b) The seed admin is not enrolled and must enrol on first login; E2E enrols programmatically. (a) is a secret in a fixture, which CLAUDE.md rule 10 only allows for "documented seed passwords". I recommend (a) with an explicit amendment to rule 10. → **Q5**

### K9 · Attachment size: is the org value a default or a cap? — **B (M1 validation of US-021/023)**

- 02 §4.1: "`default_attachment_max_mb` (1–100, default 25)". 02 §4.2: "settings.attachment_max_mb | int ≤ org default".
- 02 §9.2: "Max size: project setting (default 25 MB, org cap 100 MB)."
- The two cannot both hold: if the project must be ≤ the org **default**, the "org cap 100" is unreachable. **Proposed fix:** rename the meaning without changing the column. The org `default_attachment_max_mb` is both the default for new projects **and** the org cap; a project may set 1…org value; the hard platform cap is 100. Change **02 §4.1, §4.2, §9.2**. → **Q6**

### K10 · Which endpoints work while MFA enrolment is pending — **B (M1)**

- 02 AC-AUTH-04: "every API call except MFA enrolment returns `403 mfa_enrollment_required`."
- 06 §2.1: "MFA enrolment pending → `403 mfa_enrollment_required` (except `/auth/*`)." `/auth/*` includes password change, recovery codes and `PATCH /auth/me`.
- **Proposed fix (behaviour → 02 wins, narrowed to what the UI needs):** allow `GET /auth/me`, `POST /auth/logout`, `POST /auth/mfa/setup` and `POST /auth/mfa/enable`; everything else returns 403. Change **06 §2.1** and the wording of **02 AC-AUTH-04**. Also add `mfa_enrollment_required: bool` to the `POST /auth/login` response. 06 §4.1 currently returns only `{mfa_required}`.

### K11 · AC-AUTH-07 wording and the missing "revoke tokens" option — **B (M1)**

- 02 AC-AUTH-07: "all of the user's sessions and API tokens' "last session" are revoked (API tokens remain valid unless the user chooses "revoke tokens")".
- 06 §4.1: `POST /auth/password/reset` takes only `{token, new_password}`.
- **Proposed fix:** a reset revokes **all sessions** and invalidates all other reset links. The body gains an optional `revoke_api_tokens: bool = false`, and the reset page offers a checkbox. Reword AC-AUTH-07 to say exactly this. Change **02 AC-AUTH-07** and **06 §4.1**.

### K12 · BR traceability gate vs phased delivery and BR-33 (P2) — **B (M0 CI)**

- 08 §4: "`tests/test_rule_coverage.py` asserts that every BR ID in 01 PRD §7 appears in at least one test".
- 08 §6.5: "BR-33 | (P2) connector tests". Most BRs are implemented only from M2 onward.
- **Proposed fix:** the gate reads a per-milestone manifest (`tests/br_manifest.py`, BR → milestone). It requires every BR of a **completed** milestone to be covered, and BR-33 is tagged P2. By M9 the manifest must contain every MVP BR. Change **08 §4**.

### K13 · Domain events: in the same transaction or after commit? — **m (M1)**

- 03 §5.2 rule 2: "Upward needs … use **domain events dispatched in-process after commit** or a read-only query interface."
- 03 §5.4: "handlers run **in the same transaction** (for consistency rules) or are converted into jobs." 04 §3.1 UoW has `dispatch_in_tx_events()` before commit.
- This matters in M1 because 05 §8.2 says "system tags created per project at project creation". `tags` belongs to `testdesign`, which sits **above** `workspace`. **Proposed fix:** `workspace` emits `ProjectCreated`; `testdesign` registers an **in-transaction** handler that creates `smoke`/`sanity`/`regression`. Reword **03 §5.2** to "in-process events (in-transaction handlers for consistency, jobs for side effects)". *(my call)*

### K14 · Product name — **B (M1 UI)**

- Kickoff: "implementing TCMS (Assay)". 01 PRD: "TCMS — Test Case Management System (working name)". The designs render `productName ?? 'TCMS'` (Login, Sidebar, Main).
- **Question:** which name appears in the UI (login title, sidebar, page titles, email sender name)? I will make it a single config value either way. → **Q7**

### K15 · Status colours and icons: 07 vs the high-fidelity designs — **m (M0 tokens)**

- 07 §6.2: "passed … `--status-pass` green 600 · skipped … slate 500 · in_progress … blue 600 · not_applicable … slate 400"; "blocked | ⛔ octagon", "not_applicable | ⊘ slash-circle".
- `design/README.md`: "passed #166534 · #DCFCE7 · #BBF7D0 · #16A34A … in progress #075985 · #E0F2FE · #BAE6FD · #0284C7 … N/A #556070 …". `CycleDetail.dc.html`/`Runner.dc.html` draw **blocked** with the slash-circle glyph, which is identical to N/A in 07.
- **Proposed fix:** take **hex values from `design/README.md`**, the high-fidelity reference per CLAUDE.md. Take **icons from 07**: octagon for blocked, slash-circle for N/A, so the two statuses never share an icon. Update the colour column of **07 §6.2** to the design hex values. *(my call unless you object)*

### K16 · Dark theme has no tokens — **m (M1 UI)**

- 07 §3: user menu "theme (light/dark/system)"; 07 §6.1: "Light and dark themes via CSS variables".
- `design/README.md` defines light values only.
- **Proposed fix:** ship **light only**. Tokens are structured as CSS variables so dark can be added without rework. The theme control is **not rendered** until dark tokens are designed, per the no-dummy-UI rule. Note the deferral in 07. → part of **Q7**

### K17 · Smaller prose-vs-prose / prose-vs-SQL items — **m** (fix the prose; SQL wins for storage)

| # | Passage A | Passage B | Fix |
| --- | --- | --- | --- |
| a | 05 §3.8 jobs: "`ix_jobs__queue (status, run_at) WHERE status='queued'`" | SQL: `ix_jobs__queue ON jobs (run_at) WHERE status = 'queued'` + `ix_jobs__running_locked` | 05 prose |
| b | 05 §3.1 invitations: columns list without `is_org_admin` | SQL `invitations.is_org_admin boolean NOT NULL DEFAULT false` and `CHECK ((project_id IS NULL) = (role_id IS NULL))` | 05 prose |
| c | 04 §4.4 note: "immutability trigger allows updates only to `approved_by`, `approved_at`, `approval_mode`" | SQL trigger also allows `submitted_by/at` changes | 04 note |
| d | 04 §5.7: "deferrable not needed because update happens before insert" | Next paragraph and SQL: "works only because `fk_test_runs_superseded_by_run_id` is DEFERRABLE" | 04 §5.7 first line (L, M3) |
| e | 03 §13 A02: "key from env (`TCMS_ENCRYPTION_KEY` …)" | 03 §16: `TCMS_ENCRYPTION_KEYS` = `k1:base64key[,k0:oldkey]` | 03 §13 → `TCMS_ENCRYPTION_KEYS` |
| f | 03 §16: `DATABASE_URL` example user `tcms` | 05 §4 app role `tcms_app` | 03 §16 example |
| g | 02 §2.2: time zone "profile setting, default browser zone" | SQL `users.time_zone text NOT NULL DEFAULT 'UTC'` | Keep column; client sends browser zone at invitation acceptance; UTC fallback. 02 wording (my call) |
| h | 02 §7.3: "explicit outcome when a step failed → failed wins **and** the request is rejected with 422" | 02 table: "Any failed \| none / any \| failed (explicit non-failed → 422)" | 02 prose (L, M4) |
| i | 04 §5.5 `compute_final_status` accepts explicit `failed` on a steps attempt with no failed step (falls through to `passed`/`incomplete`) and checks `explicit == "in_progress"` for text | 06 §4.7 finalize: `passed\|failed (text only)` | Reject explicit `passed`/`failed` for steps format with `422 outcome_conflicts_with_steps`; fix 04 pseudocode (L, M4) |
| j | 02 AC-DEF-01: open → fixed by a developer → "`403 transition_not_permitted`" | 02 §8.2: open → fixed is not a transition for anyone | Order: unknown (from,to) → `422 invalid_transition`; known but not permitted → `403`. Reword AC-DEF-01 to use in_progress → fixed by a non-assignee developer (L, M5) |
| k | 02 §4.2: "Archiving a project … (or the dialog offers to close them)" | 06 §4.3 `POST /projects/{id}/archive {confirm_key}` has no close option | M1: no cycles exist yet. M3: return `409` listing open cycles, add `close_open_cycles` option (L, M3) |
| l | 03 §2 "FastAPI 0.11x"; ADR-002 "React 18" | Current upstream: FastAPI is past 0.11x; shadcn/ui CLI defaults target React 19 + Tailwind v4 | Stack note, not a doc conflict: I will pin the current FastAPI 0.x and keep **React 18** as specified (shadcn components work with 18); Tailwind version is unpinned in the docs, I will use v4. Update 03 §2 to the pinned versions at M0 |

---

## 2. Gaps that would block implementation

These are new gaps only; README open items 1–5 are not repeated.

### Need your decision

| # | Gap | Why it blocks | Proposal |
| --- | --- | --- | --- |
| **G3** | **No storage for the pending-MFA login state and its "5 failed MFA attempts" limit** (02 §3.3 step 5). 03 §9.1 mentions only "short-lived pending cookie (5 min)" signed with `TCMS_SECRET_KEY`. | A signed cookie cannot count failures: the same cookie can be replayed. | Store the pending login as a `sessions` row with `mfa_verified=false` and a 5-minute expiry; the column already exists. **Add `sessions.mfa_failed_attempts smallint NOT NULL DEFAULT 0`** in migration 0002, and update 05 §3.1 plus a new `docs/schema/03_m1_additions.sql`, so docs keep an executable form. → **Q8** |
| **G4** | **Auth rate limit storage.** 03 §13: "PostgreSQL-backed token bucket for auth endpoints only". The baseline has no table for it. | 02 §3.3 "20 auth requests/min per IP" covers login, MFA verify, forgot, reset and invitation accept. `login_attempts` records only logins. | **Add `auth_rate_limits(bucket_key text PK, window_start timestamptz, count int)`**, a fixed one-minute window per IP, in the same migration 0002. The general limit of 600/min/user stays in-memory per process, as 03 §13 says; I will document that it is per worker process. → **Q8** |
| **G10** | **The repository is not a git repository, and no CI platform is named.** M0 requires "CI pipeline with all gates", and the workflow requires branches `milestone/mN-…`. | I cannot branch or write CI until both are settled. | `git init` on `main` with an initial commit of the current spec package, then branch `milestone/m0-foundations`. CI = **GitHub Actions** (01 DEP-07 lists it first). No remote is configured and nothing will be pushed until you say so. → **Q9** |
| **G12** | **Admin "copy invite link" fallback** (09 §6: "Mailpit locally; admin 'copy invite link' fallback") vs invitation tokens stored hashed. | The link can only be shown when it is created. | Return `accept_url` **once** in the `POST /organization/invitations` response, like an API token, and show it with a copy button. Never return it from list endpoints. Add to 06 §4.2. → **Q10** |
| **G13** | **Password change side effects are unspecified** (06 `POST /auth/password/change`). | Security behaviour. | Revoke all **other** sessions, keep the current one, audit `auth.password_changed`, and email a notice. → **Q10** |
| **G6** | **Error codes M1 needs are missing from the 06 §3 catalog.** | API Spec owns codes; I should not invent them silently. | Add to 06 §3: `422 token_invalid` (reset/invitation token unknown, used or expired), `422 password_policy`, `409 last_org_admin`, `409 last_qa_manager`, `409 already_member`, `409 user_exists` (email belongs to an active user or another org), `409 mfa_already_enabled`, `409 mfa_required_by_policy` (disable refused), `422 confirmation_mismatch` (archive key), `422 invalid_transition` reused for release status. → **Q10** |

### I will resolve these as proposed unless you object (code structure → LLD)

| # | Gap | Resolution (doc to update) |
| --- | --- | --- |
| G1 | **Failure bookkeeping vs UoW rollback.** 04 §3.1 rolls back on any exception, but AC-AUTH-03 needs the failed attempt, the lockout counter and `auth.login_failed`/`auth.locked` audit to **persist while returning 401/423**. The same holds for MFA failures. | Security bookkeeping runs in its own short UoW, committed before the error is raised (`identity.security_log`). Document it in 04 §3.1. |
| G2 | **Writes during GET requests:** `sessions.last_seen_at` touch (03 §9.1 "at most once per minute"), `api_tokens.last_used_at`, and `project.admin_accessed` (K1) vs read-only GET transactions. | Authentication runs in a separate short write transaction before the request's UoW. Document it in 04 §3.1/§3.3. |
| G5 | **Audit for unknown-email login failures:** `audit_events.organization_id NOT NULL`, but an unknown email has no organization. | Unknown email: `login_attempts` row only. Known user: `auth.login_failed` audited in the user's organization. Document it in 02 §13.1. |
| G7 | **No default privileges for tables created after the baseline.** The baseline grants `ON ALL TABLES` at execution time only. Verified: `pg_default_acl` is empty, so `tcms_app` would get no rights on tables added in later migrations. | A migration helper `grant_app(table, append_only=False)` is mandatory in every migration, plus a test asserting `tcms_app` privileges on every table match 05 §4. No baseline change. Document it in 05 §8. |
| G8 | **`alembic check` cannot see triggers, functions, CHECK constraints or expression indexes**, but it does flag tables without models. | M0 writes ORM models for **all ~55 baseline tables** in their owning modules so `alembic check` is clean. Expression indexes are excluded via `include_object` (documented). The **real** guard is a `pg_dump --schema-only` diff between a DB built from `docs/schema/*.sql` and one built by Alembic, plus `99_verify.sql`. Both run in CI (`make schema-check`). |
| G9 | **Executing `01_baseline.sql` verbatim from Alembic:** the file has its own `BEGIN; … COMMIT;`, which conflicts with Alembic's transaction. | Migration 0001 reads `docs/schema/01_baseline.sql` and `02_seed_system.sql` and strips only the outer `BEGIN`/`COMMIT`. The schema diff proves equivalence. The SQL files stay the single source. |
| G11 | **Python permission catalog vs `02_seed_system.sql`** are two copies of the same matrix (02 §3.2). | The Python registry is code; a test asserts DB `role_permissions` equals the Python role map exactly. |
| G14 | `job_status` has both `failed` and `dead`; semantics are unstated. | `failed` = permanent error raised by a handler (no retry). `dead` = retries exhausted. Retryable failures go back to `queued` with backoff. Document it in 03 §10. |
| G15 | CSRF on unauthenticated POSTs (login, forgot, reset, accept invitation) has no CSRF cookie yet. | These endpoints require an `Origin`/`Referer` matching `TCMS_BASE_URL` (03 §16 already mentions "CSRF origin check"). Document it in 06 §2.1. |
| G16 | Bootstrap "prints a one-time setup link" (02 §14 W1) has no mechanism. | `tcms bootstrap` creates the org plus an **invitation** with `is_org_admin = true`, 7-day expiry, and prints its accept URL. No new table. |
| G17 | Common-password list (NFR-SEC-01 "bundled common-password list") has no source named. | Vendor a public, permissively licensed top-100k list (for example from SecLists, MIT) as a package data file. |
| G18 | 03 §9.2 "per-session cache invalidated by `MembershipChanged`" has no shared cache (no Redis by design). | MVP resolves permissions **per request** only (one indexed query). No cross-request cache, so nothing can go stale. Note it in 03 §9.2. |
| G19 | `AccessContext` needs project status for `409 project_archived` (AC-WS-02) in modules below `workspace` (for example `identity` for member writes). | `project_context_from` puts `project_status` into `AccessContext` (core). Modules check it without importing `workspace`. |

---

## 3. Implementation plan

Branches: `milestone/m0-foundations`, `milestone/m1-identity-workspace`, then `milestone/mN-<slug>`. Small Conventional Commits. No push or merge without your approval. Each milestone ends with `make lint test` (and `make e2e` when UI changed), `make schema-check` (baseline diff + `99_verify.sql` as `tcms_app`), a manual run-through on `make up`, updates to `docs/ops/` and `docs/ops/CHECKLIST.md`, and a summary.

### 3.1 M0 — Foundations (E01: US-001…006) — detail

| # | Work | Notes / acceptance hook |
| --- | --- | --- |
| 1 | `git init`, `.gitignore`, `.editorconfig`, `.env.example`; branch `milestone/m0-foundations` | After Q9 |
| 2 | **Backend skeleton** (`backend/`, uv, Python 3.12): `pyproject.toml` with ruff, mypy (strict on `rules`/`service`), pytest + xdist + testcontainers, Hypothesis, factory_boy. Packages per 04 §1 (`core`, `api`, `identity` … `platform`, `seed`). **import-linter contracts** encoding the 03 §5.1 graph, with models/repositories private | US-006: a test runs `lint-imports` against a fixture with a forbidden import and expects failure |
| 3 | **`tcms.core`**: settings (pydantic-settings, every 03 §16 var), structlog JSON + request-ID middleware (`X-Request-ID`), engine/session factories (app URL; maintenance URL; statement timeout 15 s API / 5 min worker), `UnitOfWork` (audit buffer, in-tx events, job enqueue, after-commit), `DomainError` hierarchy + RFC 9457 handler (unknown route, Pydantic `errors[]`, `P0001 immutable_record` → 409 logged at ERROR), `Principal`/`AccessContext`, permission registry (02 §3.1 catalog + 02 §3.2 role map), `ids.new_id()` (UUIDv7), `clock.now()`, pagination/filter/sort helpers with allow-lists (`400 invalid_filter/invalid_sort`), `check_row_version`, `ScopedQuery` | US-002 tests: unknown route, validation error and each `DomainError` subclass → problem+json with `code` + `request_id` |
| 4 | **Alembic**: `env.py` on `DATABASE_MAINTENANCE_URL`; migration `20261104_0001_baseline.py` executes `01_baseline.sql` + `02_seed_system.sql` (G9); `tcms migrate`; `grant_app` helper (G7) | `alembic upgrade head` from empty |
| 5 | **ORM models for every baseline table** in their owning module (G8), enums as `StrEnum` mapped to existing PG types | `alembic check` clean |
| 6 | **Schema guard** `make schema-check`: DB-A from `docs/schema/*.sql`, DB-B via Alembic → normalized `pg_dump --schema-only` diff (ignoring `alembic_version`), then `99_verify.sql` as `tcms_app` on DB-B; role-map drift test (G11); privilege test (G7) | M0 acceptance: schema matches baseline; 99_verify passes as `tcms_app` |
| 7 | **US-003 SQL tests** in pytest: immutability of versions, steps, final results/step results, append-only tables, set-once approval, purge function (wrapping and extending `99_verify.sql`) | `test_br_06_final_result_immutable_sql`, `test_br_26_audit_append_only_sql` |
| 8 | **Jobs** (`platform/jobs`): `enqueue_job`, `@job_handler`, worker loop (`FOR UPDATE SKIP LOCKED`, N threads), backoff `min(2^n·30 s, 4 h)`, `dead` after `max_attempts`, dedupe key, stale-`running` requeue after 15 min, scheduler loop with a code cron table; `tcms worker` | US-004: failing job retried with backoff then `dead`; dedupe prevents duplicates |
| 9 | **Audit recorder** (`uow.audit`, diff with redaction, `render.py`) | `test_br_26_audit_in_same_transaction` (rollback → 0 audit rows) |
| 10 | **Attachments skeleton**: S3 client, bucket check, streaming upload with size limit + SHA-256 + MIME sniff, as service functions tested against MinIO. **No route yet**: the first owning entity arrives in M2 | Used by `/health/ready` |
| 11 | **API app**: factory, `/api/v1/health/live`, `/api/v1/health/ready` (DB, migration head, S3 → 503 when down), `/api/v1/openapi.json` | `/meta/*` need auth → M1 |
| 12 | **Seed CLI skeleton**: `tcms seed --profile dev\|e2e\|large`, registry of steps, idempotent. In M0 it has no domain services to call, so it seeds nothing beyond the system roles created by the migration and says so. Writes go only through services (CLAUDE rule 2); M1 adds the org, users and SPARK | `make seed` succeeds |
| 13 | **Docker**: backend multi-stage image (api/worker/migrate/cli, includes libmagic); web image (nginx, prod); compose: `db` (postgres:16, init script runs `00_roles.sql` + creates DB, passwords from `.env`), `migrate` (one-shot), `minio` + bucket init, `mailpit`, `api` (reload, :8000), `worker`, `web` (Vite dev :5173 proxying `/api`); healthchecks | US-001: web :5173, api :8000, Mailpit UI |
| 14 | **Makefile**: `up down logs migrate seed test e2e lint api-client schema-check` (GNU make 3.81-compatible) | |
| 15 | **Frontend scaffold** (`frontend/`, pnpm): Vite, React 18, TS strict, Tailwind, shadcn/ui init, TanStack Router/Query, `openapi-typescript` + `openapi-fetch` client wrapper (base URL, credentials, CSRF header, problem+json → `ApiError`, 401 handling), `styles/tokens.css` from `design/README.md` (K15), `StatusBadge`, `ProgressBar`, `Metric` with Vitest tests, ESLint/Prettier. **AppShell** is structural layout only: product name, no navigation entries, no controls, until M1 adds real ones | US-005: `make api-client` + drift check |
| 16 | **Playwright** scaffold: one smoke test (shell loads, API health OK) + axe check | Wires the E2E gate |
| 17 | **CI** (GitHub Actions, after Q9): lint+types → unit → integration+API (testcontainers) → schema-check → OpenAPI drift → build images → E2E (Chromium) + axe. Contract/Schemathesis job on main; nightly placeholders are **not** added until they have content | All gates wired; green |
| 18 | **Docs**: `docs/ops/local-setup.md`, `environment.md`, `migrations.md`, `testing.md`, `known-limitations.md`, `CHECKLIST.md`; 05/03/04 prose fixes from K17/G7/G8/G9/G14 | DoD 8 |
| 19 | **Verify acceptance**: timed clean run (`docker system prune` for project images, then `make up && make migrate && make seed` < 10 min), `alembic check`, schema diff, 99_verify, problem+json unknown route, job retry test | Report timings in the summary |

M0 acceptance → evidence: `make up && make migrate && make seed` < 10 min (timed log); `alembic check` clean; schema diff empty + 99_verify 35/35 as `tcms_app` in CI; unknown route → problem+json (API test); job retry + dead-letter (integration test).

### 3.2 M1 — Identity, access and workspace (US-010…029, US-160 + US-161/US-164 backend per K4) — detail

Order: backend slices A→F with tests first, authz-matrix entries per route, regenerate client, then the frontend (G), then E2E.

| Slice | Stories | Backend | Tests (TCMS / BR / AC) |
| --- | --- | --- | --- |
| A · Sessions & access | US-010, 011, 016, 018, 019 | Argon2id + common-password list; `POST /auth/login` (dummy hash on unknown email for timing), lockout from `login_attempts` (10/15 min → 15 min), auth rate limit (G4), sessions (hashed token, idle/absolute, touch ≤ 1/min via G2), CSRF double-submit + origin check (G15), logout, `GET/DELETE /me/sessions`, `GET/PATCH /auth/me`, password change (G13); permission resolution (org admin flag + project role, per request, G18), `project_context_from`, `ScopedQuery`; **authz matrix harness** with guard test "every route is in the matrix"; cross-tenant fixture (two orgs, identical keys) | TCMS-001 (API part), 002, 003, 009, 012, 013, 014; AC-AUTH-01/02/03/06 |
| B · MFA | US-012, 013 | `/auth/mfa/setup\|enable\|verify\|disable\|recovery-codes`; TOTP (pyotp, ±1 step, replay via `last_used_step`); AES-GCM with key-ID prefix and `TCMS_ENCRYPTION_KEYS` ring; 10 hashed recovery codes; pending login (G3); forced-enrolment gate with allow-list (K10); org policy `mfa_required_for_all` | TCMS-004, 005, 006; AC-AUTH-04/05; secrets-encrypted-at-rest DB inspection test |
| C · Email, reset, invitations, bootstrap | US-014, 015, 020 | `email.send` job + Jinja2 templates (txt/html) via Mailpit; forgot (always 202) / reset (single use, 60 min, revokes sessions, optional token revoke per K11); invitations (7 days, optional project + role, `accept_url` once per G12), accept → user + org membership (+ project membership), `GET /auth/invitations/{token}`; `tcms bootstrap` (G16) | TCMS-007, 008; AC-AUTH-07 |
| D · API tokens | US-017 | `/me/api-tokens` (shown once, `tcms_` + 40 chars, SHA-256, scope ∩ permissions, optional project restriction, expiry ≤ 365 d, `last_used_at`), bearer auth ignores cookies | TCMS-010 |
| E · Organization & users | US-021, US-164 (backend), US-160, US-161 | `GET/PATCH /organization` (validation ranges 02 §4.1; K9), `/organization/members` + deactivate/reactivate/reset-mfa/revoke-sessions/admin flag (last-admin and self protections), `/organization/invitations`, `GET /organization/roles`, `GET /meta/enums`, `GET /meta/permissions`; audit write everywhere + `GET /audit-events/entity/{type}/{id}` | TCMS-011; TCMS-130/132 for M1 routes (parameterized "every mutating endpoint writes audit") |
| F · Workspace | US-022…026, 028, 029 | `POST/GET/PATCH /projects` (key upper-cased, `409 project_key_taken`, creator → QA Manager member, environments QA + Staging, `key_sequences` rows, system tags via in-tx `ProjectCreated` handler (K13)), settings (US-023, audited `project.settings_changed`), archive (confirm key) / restore + `409 project_archived` on every project write (AC-WS-02), members (`BR-29` default Viewer, last QA Manager protected), environments (archive/restore), releases (transition table 02 §4.4, `released_at`), activity feed (rendered summaries, filter by entity type/user), `GET /projects/{id}/resolve` | TCMS-020, 021, 022, 023, 024, 025a (K3); `test_br_27_project_key_format`, `test_br_29_new_member_default_viewer`, `test_br_25_stale_row_version_409` (M1 resources) |
| G · Frontend | US-010…017, 021–029 | Auth: login, MFA code, recovery code, forced enrolment (QR, secret, recovery codes with download + "I've saved these"), forgot, reset, invitation accept. **AppShell**: sidebar with only built items, collapse persisted, project switcher (`G P`), breadcrumbs, user menu (profile, API tokens, sessions, MFA, sign out). **Projects** list + create (K5), project **Activity** page, **project settings**: General, Options, Members, Environments, Releases, Danger zone. Administration **Invitations** + **Security policy** if Q4 = (a). `usePermission`, conflict dialog for 409 stale, empty/loading/error states, axe-clean | TCMS-001, 004, 005, 008, 020 as Playwright E2E + axe; Vitest for forms/hooks |
| Seed | — | `tcms seed --profile dev`: ACME org, users per role (seed password; admin per Q5), project SPARK with environments and releases; `--profile e2e` per 08 §3 (SPARK + HELIOS, one user per role per project). Through services only | `make seed` idempotent |

M1 acceptance → evidence: TCMS-001…014 and 020…025(a) pass; authz matrix enforced for all M1 routes; manual walk-through on `make up`: bootstrap → admin sets password and enrols MFA → invites QA Manager (Mailpit) → accepts → creates SPARK → adds members → signs in with MFA.

### 3.3 M2–M9 — outline (from 09, with what this review changes)

| Milestone | Stories | Key work | Review items to settle first |
| --- | --- | --- | --- |
| **M2** Repository & cases (3 wk) | US-040…045, 050…060, 065…069 | Folders (materialized path/depth, moves, counts), case CRUD + content normalization/hash, versions/compare/restore, approval workflow + grandfathering, tags, links, duplicate, attachments route (cases/steps, BR-28), comments + mentions, bulk (> 200 → job), purge; repository screen, case editor (StepGrid keyboard), case detail/versions/compare/review | K17c; dark theme still deferred |
| **M3** Plans & cycles (2 wk) | US-070…074, 080…087 | Plans (exit rules as structured readiness rules), selection with exclusion report, clone; cycles (BR-03 pinning, > 500 runs job, add/remove, assign/claim, reorder, start/close/reopen/clone/archive, sync from plan, update-versions, replace run); cycle detail; project archive with open cycles (K17k) | K3 (TCMS-025b), K17d, K17k |
| **M4** Runner (3 wk) | US-090…100 | Attempts (start/take-over/record/finalize/discard), roll-up rules + exhaustive matrix (TCMS-071), retest, correction, text format, evidence paste, runner UI (queue, keyboard, auto-advance, save indicator), My Work; large seed generator (TM-4); step-save p95 < 200 ms on interim large seed | **K2**, K17h, K17i; landing switches to My Work (K5) |
| **M5** Defects (2 wk) | US-110…117 | Defect CRUD, transition table as data + 13×13 × profiles matrix, prefill from result, link existing, needs_retest via in-tx event, verify prompt, history, watchers, list/kanban/detail, bulk | K17j |
| **M6** Requirements, RTM, search (2.5 wk, may run parallel after M2) | US-120…123, 130…133 | Requirements hierarchy, links both sides, coverage SQL + Python oracle property test, RTM + export, global search (FTS + trigram), filters on all lists, saved views, command palette | — |
| **M7** Reporting & readiness (2.5 wk) | US-140…146, 170, 171 | `reporting/metrics.py` + oracle property test, manager/engineer/quality/org dashboards, snapshot job, six reports + CSV/XLSX (sync ≤ 10k, job beyond; formula-injection guard), readiness + immutable decisions, release page, notifications (in-app + email digests, opt-out) | Landing switches to overview where applicable |
| **M8** Import/export, admin, hardening (3 wk) | US-150…154, 161…166 (UI), 180…184 | Import wizard (mapping, dry run, all-or-nothing commit, templates), exports, admin screens (users, roles matrix, audit log, access review, system/jobs), audit retention under maintenance role, performance tuning on large seed (k6 P1–P6), security hardening (headers, ZAP, ASVS L2, dependency scans), accessibility pass, backups + restore drill, prod compose + Caddy, runbooks | — |
| **M9** Pilot & go-live (2 wk + buffer) | US-185 | SPARK import, training, 2-week UAT per 08 §12, pilot fixes, production deployment, go-live decision recorded in TCMS | — |

---

## 4. Environment check (this machine: macOS 27.0.1, arm64)

| Tool | Required | Found | Status |
| --- | --- | --- | --- |
| Docker Engine | yes | 29.8.0, daemon running | ✅ |
| Docker Compose | v2+ | v5.5.1 | ✅ |
| PostgreSQL 16 image | yes | `postgres:16` → 16.15 pulled; baseline + 99_verify verified (35/35) | ✅ |
| Python 3.12 | yes | 3.12.16 (`python3.12`); note default `python3` is 3.9.6, so everything will run through uv-managed 3.12 | ✅ |
| Node 20+ | yes | v24.21.0 | ✅ |
| **pnpm** | yes | **not installed**; corepack 0.36.0 is present | ❌ → `corepack enable pnpm` (or `brew install pnpm`) |
| **uv** | yes | **not installed** | ❌ → `brew install uv` (Homebrew 7.0.11 present) |
| GNU make | yes | 3.81 (old Apple build) | ✅, Makefile will avoid make ≥ 3.82 features |
| git | yes | 2.54.0, but **this directory is not a git repository** | ⚠️ → Q9 |
| psql client | optional | not installed | ✅ not needed; tooling uses `docker exec` / containers |
| gh CLI | optional | not installed | Needed only if you want me to open PRs later |

Images used (all publish arm64): `postgres:16`, `minio/minio`, `minio/mc`, `axllent/mailpit`, `node`, `python:3.12-slim`, `nginx`.

---

## 5. Decisions needed from you

Each line has my recommended default. Reply "approve with defaults" or override by number.

| # | Decision | Recommended default |
| --- | --- | --- |
| **Q1** (K1) | When is an Org Admin's access to a non-member project audited? | Once per session per project, as `project.admin_accessed` |
| **Q2** (K2) | Does a step-derived **Blocked** require a reason, as the DB CHECK demands? | Yes, every final blocked/skipped/N/A needs a reason; update 02 §7.3 and BR-10 wording (confirm any time before M4) |
| **Q3** (K5) | Landing page before My Work exists (M1–M3) | Last project's Activity page; with no projects, the Projects list. Adjust TCMS-001 expectation |
| **Q4** (K6) | Invitation UI in M1 | Minimal Administration › Invitations + Security policy pages in M1; rest of Admin in M8 |
| **Q5** (K8) | Seeded Org Admin and mandatory MFA | Pre-enrolled with a documented dev-only TOTP secret, refused in production; amend CLAUDE.md rule 10 to allow it |
| **Q6** (K9) | Meaning of org `default_attachment_max_mb` | Default for new projects **and** org cap; project 1…org value; platform cap 100 |
| **Q7** (K14, K16) | Product name shown in the UI; dark theme | Name: tell me ("TCMS" or "Assay"), one config value. Dark theme deferred; theme control not rendered |
| **Q8** (G3, G4) | M1 schema additions | Migration 0002 adds `sessions.mfa_failed_attempts` and table `auth_rate_limits`; update 05 and add `docs/schema/03_m1_additions.sql` |
| **Q9** (G10) | Git and CI | OK to `git init` (initial commit = current spec package) and use GitHub Actions; no remote until you say |
| **Q10** (G6, G12, G13) | M1 API additions | Accept the error codes listed in G6, `accept_url` returned once on invite, and password change revokes other sessions |
| **Q11** (§4) | Local installs | OK for me to run `brew install uv` and `corepack enable pnpm` |
| **Q12** (K-items marked *my call*, G1–G19 "resolve as proposed") | Doc fixes and LLD-level resolutions | Apply them in the M0/M1 branches, with the doc edits in the same branch |

After approval I will start M0 on `milestone/m0-foundations` and stop when the M0 acceptance criteria pass, or earlier if any point above turns out to be wrong.
