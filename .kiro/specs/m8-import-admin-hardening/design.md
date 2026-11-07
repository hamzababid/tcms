# M8 — Import/export, administration, hardening · Design

**(Q)** = needs the product owner's answer before building; the rest are my calls and can be overridden.

| # | Topic | Decision | Why |
| --- | --- | --- | --- |
| D1 | PR split (Q1 = a, product owner 2026-11-06) | **(a, chosen)** Three PRs: **M8a** import/export (E14), **M8b** administration (E15 UI + retention), **M8c** hardening (E17: deployment, backups, performance, security, accessibility). **(b)** Two PRs: M8a import/export + administration, M8b hardening. **(c)** One PR | M8 is the largest milestone (3 weeks); hardening touches CI and deployment and is easier to review alone |
| D2 | Requirement import (Q2 = a, product owner 2026-11-06) | **(a, chosen)** CSV/XLSX of references: reference, title, link, linked case keys; same layout for export; same wizard as cases (fewer steps). **(b)** No file import; "paste many" stays the only way in, plus the export | ADR-024 removed requirement text; docs/02 §15.3 still lists type, owner, status, parent |
| D3 | Deployment check (Q3 = a, product owner 2026-11-06) | **(a, chosen)** Verify the production compose locally: Caddy with its internal certificate on `https://localhost`, full smoke suite against it, backup and restore drill on the same machine. A real staging host and domain are verified in M9 (pilot). **(b)** You give me a staging host/domain now and I verify there | US-180 says "runbook verified on staging"; I have no access to a server |
| D4 | Import pipeline | docs/04 §10.3: upload → `data_transfers(kind=import, status=uploaded)` with the file in S3 → `validate` job (openpyxl read-only / csv) builds an `ImportPlan` (folders to create, cases create/update/unchanged, errors ≤ 1,000 stored) → `validated` → `commit` job re-validates and writes everything in **one transaction** through the testdesign services (`bulk_operation_id` = transfer id), flushing every 500 cases → `committed` + report CSV. Any exception rolls back the whole file (AC-IMP-03) | One code path for rules and audit |
| D5 | Mapping templates | New table `import_mappings` (id, org, project, entity, name, mapping jsonb, created_by/at; unique per project+entity+name) — migration 0005 | docs/05 has no table for them; project settings jsonb would mix config and data |
| D6 | Synonyms and value maps | Built-in synonyms per field (e.g. Summary/Name → title; Expected/Expected Result → step expected; Module/Path → folder). Enum columns show the distinct file values and let the user map each to an allowed value (P1 → high) | docs/07 §5.16 mock |
| D7 | Case export | `POST /projects/{id}/exports {entity: test_case, format, filters | case_ids, version: latest|approved}`; ≤ 10,000 rows sync, else background (M7 transfer path). Columns = the import's canonical headers, so export → import is a no-op (AC-IMP-02, TCMS-135) | One layout both ways |
| D8 | Admin API | Add the missing docs/06 §4.2 routes: `GET /organization/access-review?format=json|csv|xlsx`, `GET /organization/audit-events` (+ `?format=csv`), `GET /projects/{id}/audit-events`, `GET /organization/system-status`, `GET /organization/jobs?status=`, `POST /organization/jobs/{id}/retry`; members list gains per-project roles | docs/06 §4.2, §4.12 |
| D9 | Retention purge | Monthly job `audit.retention` using a separate engine on `DATABASE_MAINTENANCE_URL` (tcms_owner, the only role the append-only trigger lets delete), per organization by its `audit_retention_years`; writes `audit.purged {before, count}` through the app role afterwards. The worker needs the maintenance URL; documented in environment.md | docs/02 §13.2, HLD §16 |
| D10 | Security headers | API middleware adds `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options: DENY` / CSP `frame-ancestors 'none'` on every response; Caddy adds HSTS and the SPA's CSP `default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'` (inline styles: Recharts/Radix) | NFR-SEC-09 |
| D11 | Rate limit | Per-user (or per-IP when anonymous) 600 requests/min, in-memory fixed window per worker process as docs/03 §13 says; `RateLimit-Limit/Remaining/Reset` headers; 429 `rate_limited` | L9; no Redis (CLAUDE.md rule 9) |
| D12 | 10× seed | `tcms seed --profile large` loads with `COPY` from generated CSV streams into staging tables, then `INSERT … SELECT` with the version-check trigger satisfied, in batches of 50,000 runs; target < 10 min | L43: the row-by-row trigger path stalled at 500k runs |
| D13 | Load tests | k6 scripts in `perf/` (P1–P6), run against the local production compose on the 10× seed; P4 soak shortened to 20 min locally (2 h on staging in M9). Results and machine spec in performance.md | docs/08 §9 |
| D14 | Scans | CI: `pip-audit`, `pnpm audit --prod --audit-level high`, Trivy on both images (fail on high/critical, documented exceptions with expiry in `security/exceptions.md`); nightly workflow: ZAP baseline against the CI stack. Authenticated ZAP full scan once, findings in `docs/ops/security-review.md` | docs/08 §4, §8 |
| D15 | Accessibility | Keep axe in every E2E; add TCMS-143 keyboard-only E2E for repository and runner; `?` opens a shortcut help dialog listing docs/07 §10 | NFR-UX-03, L20 |

## Tests (docs/08)

| Test | Where |
| --- | --- |
| TCMS-130 every mutating endpoint writes audit | API: parameterised over the authz matrix's write routes |
| TCMS-131/132 append-only, rollback leaves no audit | exist (M1) — re-verified |
| TCMS-133 access review contents | API |
| TCMS-134 dry run reports row errors | API + E2E (wizard) |
| TCMS-135 export → re-import unchanged | API |
| TCMS-136 import all-or-nothing | integration (fault injection mid-commit) |
| TCMS-137/138 upload limits, Markdown XSS | exist (M2) — re-verified; ZAP |
| TCMS-139 dead job listed and retried | API + E2E (System page) |
| TCMS-140 health ready fails when DB down | integration |
| TCMS-141 backup restore drill | scripted drill, logged |
| TCMS-142 performance P1–P6 | k6, logged |
| TCMS-143 keyboard-only runner and repository | E2E |
