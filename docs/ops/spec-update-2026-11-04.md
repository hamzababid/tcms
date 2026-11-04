# Spec update 2026-11-04 (v1.0 → v1.3): merge report

| Field | Value |
| --- | --- |
| Date | 2026-11-04 |
| Pack | `spec-update-2026-11-04/` (UPDATE.md, CHANGES.md C01–C23, 7 patches, `new/`, `reference/`) |
| Branch | `docs/spec-update-2026-11-04`, created from `milestone/m1-identity-workspace` (commit `ddd7c3a`) so the merge starts from the newest version of every doc. Neither branch is pushed or merged yet |
| Result | All 23 changes present; 1 change applied by intent (C21); `docs/brand/` added; nothing needs a decision |

## Key finding

This repository's **initial commit (`8e54e9b`) already contained the v1.3 text** of the seven changed files, plus `docs/schema/` and `docs/design/`. It did not contain `docs/brand/` or the brand row in the README index. So 22 of the 23 changes were already present before this merge, and the only actual edits are the README brand row (C21) and the new `docs/brand/` folder.

`reference/` was used only for comparison; no file was copied from it.

## Patches (`git apply`)

Each patch was dry-run first (`git apply --check`, then `git apply -R --check`). A patch whose reverse applies cleanly is already in the file, so `git apply --3way` was not run on those (it would only conflict).

| Patch | Result |
| --- | --- |
| `CLAUDE.patch` | Already applied (reverse applies cleanly) |
| `docs_03-HLD.patch` | Already applied |
| `docs_04-LLD.patch` | Already applied |
| `docs_09-Implementation-Roadmap.patch` | Already applied |
| `docs_11-Decision-Log.patch` | Already applied |
| `README.patch` | Does not apply either way (README was edited after the change; the index has an extra `ops/` row and lacked the brand row). Handled change by change below |
| `docs_05-Database-Design.patch` | Does not apply either way: the C01 sentence was extended in M1 (`03_m1_additions.sql`). Handled change by change below |

## Changes C01–C23

| Change | File | Status |
| --- | --- | --- |
| C01 | docs/05 | **Already present, with a later repo edit kept.** The sentence also lists `03_m1_additions.sql` (added in M1 with migration 0002). All C01 content is present; the addition does not contradict it |
| C02–C14 | docs/05 | Already present verbatim; v1.0 find-text absent |
| C15 | docs/03 | Already present verbatim |
| C16 | docs/04 | Already present verbatim |
| C17 | docs/09 | Already present verbatim |
| C18 | docs/11 | Already present verbatim |
| C19, C20 | CLAUDE.md | Already present verbatim |
| C21 | README.md | **Applied by intent.** The schema and design rows already existed (between the CLAUDE.md and PRD rows); the brand row was missing. Inserted `\| — \| [brand/](docs/brand/) \| Assay logo kit: SVG/PNG logos, app icon, favicon, colours, usage rules \|` after the schema row, which matches the C21 order (schema, brand, design). No other README text changed |
| C22 | README.md | Already present verbatim (open items renumbered 1–5, Jira item removed) |
| C23 | README.md | Already present verbatim (exactly one "Decided on 2026-11-04" line) |

## New folders

| Folder | Result |
| --- | --- |
| `docs/schema/` | Already in the repo. **Compared file by file:** `00_roles.sql`, `01_baseline.sql`, `02_seed_system.sql` and `99_verify.sql` are byte-identical to the pack. The repo has one extra file, `03_m1_additions.sql` (M1 additions, migration 0002); it was kept. Nothing overwritten |
| `docs/design/` | Already in the repo. **Compared file by file:** all 13 files are byte-identical to the pack. Nothing changed |
| `docs/brand/` | **Added** (16 files + `png/` with 20 PNGs), identical to `new/docs/brand/`. Its colours (Assay Indigo #4F46E5, Ink #0F172A, Night #111827) match the tokens already in `frontend/src/styles/tokens.css` |

## Needs decision

None. No repo edit contradicts a change in CHANGES.md.

## Verification

| Check | Result |
| --- | --- |
| Every change C01–C23 present | ✅ Script check: every replacement line is in its file, no v1.0 find-text remains (C01 checked by its phrases because of the M1 addition) |
| Repo edits since v1.0 preserved | ✅ The merge commit only adds content: 36 files, 63 lines added, **0 deleted**; the only modified file is README.md (+1 row) |
| Internal links resolve | ✅ for every link this update touches (schema, design, brand, ops). Three pre-existing references were reported but **not changed**, because CHANGES.md does not mention them: `attachment:<uuid>` in docs/02 is example syntax, not a link; `docs/seed/tcms-regression.csv` in docs/08 §15 has never existed (08 says it is generated from the catalog; no generator yet); `docs/01` in docs/ops/00-review.md is part of the label "`docs/01`–`12`" |
| Pack SQL on PostgreSQL 16.15 | ✅ Fresh `postgres:16` container: `00_roles.sql` (superuser), `01_baseline.sql` and `02_seed_system.sql` as `tcms_owner` without errors, then `99_verify.sql` as `tcms_app`: **35 PASS, 0 FAIL/ERROR** |
| Alembic migrations vs `01_baseline.sql` | ✅ `backend/tests/integration/test_schema.py`: 5 passed. Migration `0001_baseline` runs `01_baseline.sql` + `02_seed_system.sql` verbatim; `alembic check` is clean; `pg_dump --schema-only` of the migrated DB equals a DB built from `docs/schema/0[1-3]_*.sql`; `99_verify.sql` passes as `tcms_app` on the migrated DB. **Difference vs `01_baseline.sql` alone:** the migration head also includes `03_m1_additions.sql` (`sessions.mfa_failed_attempts`, table `auth_rate_limits`), approved in the Step 0 review (Q8). No migration was changed |

## Repo edits since v1.0 that were preserved

All of these are untouched by this merge (`git diff 8e54e9b ddd7c3a`, excluding docs/ops):

| File | Edits (milestone) |
| --- | --- |
| CLAUDE.md | Rule 10: documented dev-only seed TOTP secret (M1, review Q5) |
| README.md | `ops/` row in the documents index (M0) |
| docs/02 | `project.admin_accessed`, AC-AUTH-04/07 wording, attachment cap (K9), W1 step 4, password change, audit action list (M1) |
| docs/03 | Pinned versions, MinIO image, `TCMS_ENCRYPTION_KEYS`, events wording, job states (M0); permission resolution, auth rate limit, CSRF origin check, pending sign-in (M1) |
| docs/04 | Version-trigger note (M0); auth transaction and `Outcome` pattern, seed description (M1) |
| docs/05 | Jobs index/status, invitations columns, baseline execution and grants, schema-diff testing (M0); C01 sentence + `03_m1_additions.sql`, `sessions.mfa_failed_attempts`, `auth_rate_limits` (M1) |
| docs/06 | MFA allow-list, CSRF/Origin, error codes, auth endpoint shapes, `accept_url`, `member-candidates` (M1) |
| docs/07 | §6.2 status colours/icons, light theme only (M0) |
| docs/08 | BR traceability gate (M0/M1), TCMS-001 landing, TCMS-025a/b (M1) |
| docs/09 | M1 scope and acceptance, M3 TCMS-025b (M1) |
| docs/schema/03_m1_additions.sql | New file (M1) |

## Not done (by design)

- No "TCMS" → "Assay" renaming in the text (UPDATE.md: only if the maintainer asks).
- The logo and favicon are not yet used by the app; that would be an application change outside this docs merge. Suggestion for a follow-up: use `docs/brand/favicon.*` and `assay-logo*.svg` in `frontend/` (sign-in card, sidebar).
- `spec-update-2026-11-04/` is left in the working tree, uncommitted, until you approve its deletion.
