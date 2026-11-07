# M8 — Import/export, administration, hardening · Requirements

| Field | Value |
| --- | --- |
| Milestone | M8 (docs/09 §2): "Production-ready release candidate". Acceptance: TCMS-130…143 pass; performance log meets targets; no high findings |
| Epics | E14 Import and export (US-150…154); E15 administration UI (US-161…166); E17 hardening (US-180…184) |
| Adapted to | ADR-023 (bug links), ADR-024 (requirement references: import = references + linked case keys, not requirement text) |
| Carried from earlier | L1 (pin MinIO), L8 (proxy client IP), L9 (general rate limit), L14 (2,000-folder tree), L19 (export bulk action, "select all matching" for plan/cycle), L20 (shortcut help), L31 (50 testers under load), L36 (project-name race → 409), L38 (list exports), L43 (10× seed) |
| Out of scope | Pilot and go-live (M9); Jira, SSO, custom roles (P2); hash-chained audit (P2) |

## E14 — Import and export

### R-150 · Case import wizard (US-150, FR-IMP-001, docs/02 §15.1)
Project settings › Import/Export and the repository's `[Import]`: 1 Upload (CSV/XLSX ≤ 20 MB, ≤ 5,000 cases, ≤ 50,000 rows; sheet picker) → 2 Map columns (auto-map by header and synonyms; enum value mapping; steps layout row-per-step or single cell; target folder; mode upsert or create-only) → 3 Validate (dry run, background: create / update / unchanged / errors with row and column; download errors) → 4 Commit (background, one transaction, report CSV). Commit stays disabled while errors exist unless "skip rows with errors". Cases are written through the testdesign services (rules and audit apply); `import.committed` with counts.

### R-151 · Mapping templates (US-151)
Save the current mapping as a named template per project; pick a template in step 2.

### R-152 · Case export (US-152, FR-IMP-002)
CSV/XLSX in the same row-per-step layout with a `Key` column, so the file re-imports as updates (AC-IMP-02); latest or approved version; respects the repository filters and selection (repository bulk action "Export", closes the export part of L19).

### R-153 · Requirement references import/export (US-153, ADR-024)
CSV/XLSX columns: reference, title, link, linked case keys (comma-separated). Import creates or updates references and links the cases; export writes the same layout from the Requirements list.

### R-154 · Other exports (US-154, L38)
Bug links and cycle runs export through the M7 reports; the Bugs and Requirements lists get `[Export]` buttons that use them.

## E15 — Administration (UI for M1 services)

### R-162 · Audit log (US-162, FR-AUD-002)
Organization audit log (`org.audit.view`) and project audit log (`project.audit.view`): filters actor, action, entity type, project, date range; event drawer with changes old → new; CSV export.

### R-163 · Access review (US-163, FR-AUD-004, TCMS-133)
One row per user × scope (email, name, active, org admin, MFA enrolled, project, role, granted by, granted at, last sign-in); preview table + XLSX/CSV.

### R-164 · Users (US-164, docs/02 §3.5)
Table: name, email, status, org admin, MFA, projects with roles, last sign-in; actions invite, deactivate/reactivate, reset MFA (reason), revoke sessions, toggle org admin; last-admin and self protections shown as disabled actions with the reason.

### R-165 · System status and jobs (US-165, TCMS-139)
Version, migration head, storage check, job queue counts (queued, running, failed, dead) with oldest age; dead and failed jobs list with retry.

### R-166 · Audit retention (US-166, NFR-CMP-01)
Monthly job deletes audit events older than `audit_retention_years` under the maintenance role and writes its own `audit.purged` event.

Also: Roles page (read-only permission matrix, docs/07 §5.13).

## E17 — Hardening

### R-180 · Production deployment (US-180, docs/03 §12)
`deploy/docker-compose.prod.yml` + `deploy/Caddyfile`: Caddy (TLS, HSTS, security headers) → web (nginx) and api (gunicorn, `--forwarded-allow-ips`, closes L8); worker; migrate one-shot; PostgreSQL; S3 (MinIO or external). Secrets from files. Runbook `docs/ops/deploy.md` (install, upgrade, rollback).

### R-181 · Backups and restore (US-181, NFR-REL-03, TCMS-141)
`deploy/backup.sh` (nightly `pg_dump -Fc` + object-store mirror, 30 daily + 12 monthly), `deploy/restore.sh`; restore drill documented and run: restore into a clean stack, run the smoke suite and integrity queries.

### R-182 · Performance (US-182, NFR-PERF, TCMS-142)
10× seed (100k cases, 500k attempts; closes L43) with a COPY-based loader; k6 scripts P1–P6 (docs/08 §9); fixes until targets are met; results in docs/ops/performance.md. Folder tree with 2,000 folders < 1 s (L14).

### R-183 · Security (US-183, NFR-SEC, TCMS-137/138)
Security headers (CSP, HSTS, frame-ancestors, nosniff, Referrer-Policy, Permissions-Policy); general per-user rate limit 600/min with `RateLimit-*` headers (L9); OpenAPI JSON behind auth in production; project-name race → 409 (L36); CI: pip-audit, pnpm audit, Trivy image scan; ZAP baseline (CI nightly) and an authenticated full scan run once with findings triaged; ASVS L2 checklist `docs/ops/asvs-l2.md` with status per requirement.

### R-184 · Accessibility (US-184, NFR-UX-03, TCMS-143)
axe on every screen (already in E2E) plus a keyboard-only run of the repository and the runner (TCMS-143); `?` shortcut help (L20); manual pass findings fixed or logged.

## Tests
TCMS-130…143 (docs/08 §15) mapped in the design; AC-IMP-01…03.
