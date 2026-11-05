# Handoff to Kiro — current state of Assay (tcms)

| Field | Value |
| --- | --- |
| Author | Kiro (taking over from Claude Code) |
| Date | 2026-11-05 |
| Scope | Read-only investigation + steering install. No application code changed. |
| Branch for this report | `chore/kiro-handoff` (not pushed) |

## 1. State summary

The previous agent (Claude Code) built the spec in `docs/` through **M2** plus a cross-cutting
**design-system pass** and a **brand-assets pass**. M3–M9 have not been started beyond the baseline
schema and ORM models that M0 created.

### Git

- **Current branch (working HEAD):** `feat/design-system` at `512a6c7`. Working tree **clean**, no stashes,
  no uncommitted or untracked application work (only the usual ignored caches: `.venv`, `__pycache__`,
  `node_modules`, `.coverage`, `dist`, test artifacts).
- **Local branches:** `main`, `milestone/m0-foundations`, `milestone/m1-identity-workspace`,
  `milestone/m2-repository-cases`, `docs/spec-update-2026-11-04`, `feat/brand-assets`, `feat/design-system`.
  Every local branch has a matching `origin/*` remote; all are already pushed and up to date.
- **Branch topology (important):** `main` is at `5b58cd8` and contains **M0 + M1 + the 2026-11-04 spec
  update only** (PRs #1, #2, #3). It does **not** yet contain M2, brand or design-system.
  The full current code lives on `feat/design-system`, whose ancestry includes the M2 merge (PR #5,
  `647bf6e`), the brand work and the design-system commits. In other words, M2/brand/design were merged
  forward onto the `feat/design-system` line but `main` was never fast-forwarded to them.
  **Open decision D1 below.**
- **Last commits (newest first):** design-system (`512a6c7`, `eb3333c`), brand authz fix (`680d2fc`),
  M2 merge (`647bf6e`) and its branch (`c9a35af`…`66e1522`), brand (`d54dcec`), spec-update merge
  (`5b58cd8`/`7f3c568`), M1 merge (`7e91831`/`ddd7c3a`…`7817fd0`), M0 merge (`2fb1f04`/`2d4552b`…`c9985b6`),
  initial commit (`8e54e9b`).

### Spec update 2026-11-04 (v1.0 → v1.3)

Merged and clean:

- `docs/schema/`, `docs/design/`, `docs/brand/` all exist.
- **ADR-020** in `docs/11-Decision-Log.md` reads **"Accepted — confirmed by the product owner on 2026-11-04"**.
- The `spec-update-2026-11-04/` pack is **no longer present** in the working tree (cleanup approved and done).
- `docs/ops/spec-update-2026-11-04.md` documents the merge: 22 of 23 changes were already present in the
  initial commit; only C21 (README brand row) and the new `docs/brand/` folder were added by that merge.

## 2. Test and verify results

All commands run on this machine (macOS, Docker 29.8.0 running, uv 0.13.7, pnpm 12.16.1, Node 24).
The `make up` output reports the web port as **5174** (host had 5173 taken), api 8000, mailpit 8025.

| Step | Command | Result |
| --- | --- | --- |
| Stack up | `make up` | ✅ all containers healthy; migrate + storage-init ran clean |
| Migrate | `make migrate` | ✅ `migrations: at head` |
| Seed | `make seed` (dev profile) | ✅ idempotent — org `acme` and SPARK already seeded ("nothing to do") |
| Schema verify | `pytest tests/integration/test_schema.py` | ✅ **5 passed**, incl. `test_verify_sql_passes_as_app_role` (**99_verify.sql = 35 PASS as `tcms_app`** on a fresh DB), `test_alembic_check_is_clean`, `test_migrated_schema_matches_docs_baseline`, `test_app_role_privileges`, `test_seeded_role_permissions_match_code_registry` |
| Backend lint | `ruff check` · `ruff format --check` · `mypy` · `lint-imports` | ✅ ruff clean · 130 files formatted · mypy "no issues in 94 files" · **import-linter 11 contracts kept, 0 broken** |
| Backend tests | `pytest -n auto -m "not timing"` | ✅ **320 passed, 98 subtests passed**, 0 failed (63 s) |
| Backend timing tests | `pytest -m timing` | ✅ **1 passed** |
| Frontend lint | `pnpm lint` · `pnpm typecheck` · `pnpm format:check` | ✅ eslint clean (`--max-warnings 0`) · tsc clean · prettier clean |
| Frontend tests | `pnpm test` (vitest) | ✅ **26 passed** (5 files) |
| E2E | `playwright test` against the live stack | ✅ **15 passed** (smoke + m1 + m2 journeys incl. MFA sign-in, project create, folders, 10-step case, version compare, review, conflict dialog) |
| Brand drift | `scripts/sync-brand.sh check` | ✅ no drift |
| API client drift | `make api-client-check` | ✅ no drift (`openapi.json` / `schema.d.ts` current) |

**Note on running `99_verify.sql` directly against the dev DB:** it fails with a
`ux_organizations__slug` duplicate-key error because the script seeds its own `acme`/fixtures and the dev
DB is already seeded. That is expected — the script is designed to run on a **fresh** database. The
canonical gate is `test_verify_sql_passes_as_app_role`, which builds a clean DB and gets 35/35. Use
`make schema-check` (not a raw psql run against the seeded dev DB) to reproduce the 35 PASS.

One non-blocking warning across the backend suite: FastAPI TestClient's `httpx`-deprecation notice
(tracked as known-limitation L7).

## 3. Milestone / story status

Derived from code (implemented module files + routes) and passing tests, not from commit messages alone.
Backend module shape: `identity`, `workspace`, `testdesign` have full
`service.py`/`rules.py`/`repository.py`/`schemas.py`. `planning`, `execution`, `defects`, `requirements`,
`reporting` contain **only `models.py`** (baseline ORM from M0) — no service/rules/router — so their
features are not started. Frontend `features/` has `auth`, `profile`, `projects`, `admin`, `testdesign` only.

| Milestone | Stories | Status | Evidence |
| --- | --- | --- | --- |
| **M0** Foundations | US-001…006 | ✅ **Done** | Stack up, `alembic check` clean, schema diff empty, 99_verify 35/35, problem+json, jobs retry/dead-letter; import-linter 11 contracts; API client + drift gate |
| **M1** Identity & workspace | US-010…029, US-160, US-161 (API), US-164 (API) | ✅ **Done** | 320 backend tests incl. authz matrix (every route × roles), TCMS-001…014/020…025a; E2E m1 (MFA sign-in, project create); frontend auth/projects/profile/admin screens |
| **M2** Repository & cases | US-040…045, US-050…060, US-065…069 | ✅ **Done** | `testdesign` full module; TCMS-030…047; E2E m2 (folders, 10-step case, compare, review, conflict); `br_manifest.COMPLETED = {M0, M1, M2}` |
| Design-system pass | — | ✅ **Done** | `styles/tokens.css`, one `DataTable`, full-width layouts, audit filters; vitest + E2E + axe |
| Brand assets | — | ✅ **Done** | favicon/manifest/logos from `docs/brand`; `make brand-check`; smoke E2E "brand assets … served" |
| **M3** Plans & cycles | US-070…074, US-080…087 | ⬜ **Not started** | `planning` has only `models.py`; no plans/cycles service, router or screens; TCMS-025b, 050…060 absent |
| **M4** Execution runner | US-090…100 | ⬜ **Not started** | `execution` has only `models.py`/`queries.py`; no runner |
| **M5** Defects | US-110…117 | ⬜ **Not started** | `defects` has only `models.py` |
| **M6** Requirements, RTM, search | US-120…123, US-130…133 | ⬜ **Not started** | `requirements` has only `models.py` |
| **M7** Reporting & readiness | US-140…146, US-170…171 | ⬜ **Not started** | `reporting` has only `models.py`; no `metrics.py` yet |
| **M8** Import/export, admin UI, hardening | US-150…154, US-162…166, US-180…184 | ⬜ **Not started** | Admin UI limited to M1 invitations + security policy |
| **M9** Pilot & go-live | US-185 | ⬜ **Not started** | — |

**Business-rule coverage** (`tests/br_manifest.py`): BR-01/02/13–18/25–29 are covered and part of completed
milestones. BR-03/04/05/11/12/31 (M3), BR-06…10/30/32 (M4), BR-19…22 (M5), BR-23 (M6), BR-24 (M7) are
mapped to their future milestones and not yet required by the coverage gate. BR-33 is tagged P2.

## 4. Deviations from the spec found in the code

No behaviour/contract deviations were found that contradict the spec. The intentional, documented
reconciliations the previous agent recorded (all in `docs/ops/00-review.md` and already reflected in the
spec text) are:

- **K1** `admin_access` → **`project.admin_accessed`** (first non-member Org-Admin access per session,
  separate write transaction); satisfies the `audit_events.action` CHECK format.
- **K17a / G7** jobs indexes and a mandatory `grant_app()` migration helper; migration **0002**
  (`docs/schema/03_m1_additions.sql`) adds `sessions.mfa_failed_attempts` and `auth_rate_limits` (G3/G4).
- **K5 / L12** post-login landing is the last project's Activity (or the project list) until My Work (M4).
- **K15** status **colours** from `docs/design/README.md`, **icons** from docs/07 (octagon = blocked,
  slash-circle = N/A) so the two never share a glyph.
- **K16 / L5** light theme only; theme toggle not rendered (no dummy UI).
- **G6** extra M1 error codes added to docs/06 §3.

These are "spec updated to match intent", not silent code drift. Full list and rationale: `00-review.md`
§1–§2; current gaps tracked in `docs/ops/known-limitations.md` (L1, L5–L9, L12–L20).

## 5. Open decisions / conflicts left open

- **D1 — `main` is behind the real code (needs a decision).** `main` has only M0+M1+spec-update.
  M2, brand and design-system live on `feat/design-system` (and `feat/brand-assets`). Before starting M3
  we should settle the branching: either fast-forward/merge `feat/design-system` → `main` and branch
  `milestone/m3-plans-cycles` from it, or branch M3 directly from `feat/design-system`. My recommendation:
  merge `feat/design-system` into `main` first so `main` is the true baseline, then branch M3 from `main`.
  **This needs your approval — I have not pushed or merged anything.**
- **Deferred spec conflicts awaiting their milestone** (from `00-review.md`, not yet due):
  K2 (BR-10 roll-up "blocked" needs a reason) and K17h/i → **M4**; K17d/k (deferrable FK, archive with
  open cycles) → **M3**; K17j / AC-DEF-01 defect transition ordering → **M5**. Confirm K2 before M4.
- **Product open items 1–5** in `README.md` remain assumptions in effect (Jira Cloud, requirements source
  of truth, data-validation format in P2, retention, automation frameworks). None block M3.

## 6. Uncommitted work found

None. The working tree on `feat/design-system` is clean; there are no stashes and no untracked
application files. Nothing of the previous agent's work is at risk — everything is committed and pushed.
(The only new files are the ones this handoff creates: `.kiro/steering/*`, this report, and the CHECKLIST
status edits.)

## 7. Recommendation: next milestone and first tasks

**Next milestone: M3 — Plans and cycles** (epics E07, E08), the strict next step in docs/09.

Suggested first tasks, in LLD implementation order (migration → models → repository → rules → service →
schemas → router → authz matrix → API client → frontend → E2E), tests first per BR/AC:

1. **Settle branching (D1)** — get approval, then establish `main` as the true baseline and create
   `milestone/m3-plans-cycles`.
2. **Confirm K2** (BR-10 "blocked/skipped/N/A roll-up needs a reason") with the product owner — it affects
   M4 but is cheap to confirm now.
3. **Plans (E07):** `planning` service for US-070 (plan with objectives/scope/environments/criteria/risks/
   dates/members, exit rules as structured rules), US-071 case selection by folder/tag/saved view/search
   (report exclusions, TCMS-051), US-073 clone, US-074 plan-cases-with-results view. Requirement links
   (US-072) stay a placeholder until M6.
4. **Cycles & runs (E08):** US-080 create-from-plan/repository with **version pinning** (ADR-018) and
   background creation for > 500 runs (TCMS-054); US-081 add/remove runs (BR-12); US-082 assign/claim;
   US-083 progress; US-084 start/close/reopen/clone/archive (BR-11); US-085 sync-from-plan (BR-31);
   US-086 update-versions / replace-run (BR-04/05); US-087 reorder.
5. **Close the M1/M2 "arrives in M3" tails:** TCMS-025b (archived environment → 422 on cycle create),
   the "all cycles closed" check for project archive (US-029), and the `409` + `close_open_cycles` option
   on project archive (K17k).
6. **Tests:** BR-03/04/05/11/12/31 (`test_br_*`), TCMS-025b and TCMS-050…060; extend the authz matrix for
   every new route; a cycle-detail E2E journey. Add M3 to `br_manifest.COMPLETED` only when its acceptance
   passes.

**M3 acceptance (docs/09):** TCMS-025b, 050…060 pass; BR-03/04/05/11/12/31 tests green; `make lint test`
and the schema gate stay green.
