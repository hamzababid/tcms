# M8 — Import/export, administration, hardening · Tasks

Q1 = a, Q2 = a, Q3 = a (product owner, 2026-11-06). This branch is M8a; M8b and M8c follow.

## M8a — Import and export
- [x] a.1 Docs: docs/02 §15 (references import per ADR-024, error list), docs/05 `import_mappings`, docs/06 §4.13 + error codes, docs/07 §5.16.
- [x] a.2 Migration 0005 `import_mappings`; parser (CSV/XLSX, sheets, row-per-step and single-cell layouts), mapping + synonyms + value maps; `ImportPlan` rules with unit tests.
- [x] a.3 Upload / validate / commit endpoints and jobs; one-transaction commit; report CSV; templates API; AC-IMP-01/03, TCMS-134/136.
- [x] a.4 Case export (`POST /exports`), re-import no-op (AC-IMP-02, TCMS-135); requirement references import/export (D2).
- [x] a.5 Frontend: import wizard (4 steps), templates, repository Import/Export, bulk Export, Bugs/Requirements Export buttons; E2E.

## M8b — Administration
- [x] b.1 API: access review (json/csv/xlsx), org and project audit events (+csv), system status, jobs list/retry, members with project roles; TCMS-130, 133, 139.
- [x] b.2 Audit retention job on the maintenance engine (D9).
- [x] b.3 Frontend: Users, Roles, Audit log (drawer, CSV), Access review, System; project Audit tab; E2E.

## M8c — Hardening
- [x] c.1 Security headers, rate limit, OpenAPI auth in prod, L36; CI scans; ZAP baseline nightly; authenticated scan + ASVS L2 checklist.
- [x] c.2 Production compose + Caddy + runbook; forwarded IPs (L8); pin images (L1).
- [x] c.3 Backup/restore scripts and drill (TCMS-141); health-ready test (TCMS-140).
- [x] c.4 10× seed loader; k6 P1–P6; tuning; folder tree (L14); performance log (TCMS-142).
- [x] c.5 Keyboard-only E2E (TCMS-143), `?` help (L20), accessibility fixes.
- [x] c.6 Close-out: checklist, known limitations, PR(s), CI green, report.
