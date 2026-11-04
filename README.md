# TCMS — Specification Package

Specification for a self-hosted, enterprise-grade Test Case Management System, written to be implemented with Claude Code and maintained by a small team. Baseline version 1.0 · 2026-11-03.

## How to use with Claude Code

1. Create the application repository and copy this package into its root (`CLAUDE.md`, `README.md`, `docs/`).
2. Open Claude Code in the repository. It reads `CLAUDE.md` automatically.
3. Build milestone by milestone, starting with: *"Read CLAUDE.md and docs/09 M0. Implement milestone M0 completely."*
4. Keep the docs in the repository and update them in the same PR whenever behaviour or contracts change.

## Documents

| # | Document | Contents |
| --- | --- | --- |
| — | [CLAUDE.md](CLAUDE.md) | Working rules, read order, non-negotiable invariants, commands |
| — | [schema/](docs/schema/) | Executable PostgreSQL 16 baseline (roles, schema, system seed) and 35 invariant checks; verified on PostgreSQL 16.15 |
| — | [design/](docs/design/) | High-fidelity UI screens and design tokens (visual reference for docs/07) |
| 01 | [PRD](docs/01-PRD.md) | Vision, objectives, personas, journeys, FR/NFR/BR catalog with IDs, scope, assumptions, dependencies, risks, MVP acceptance |
| 02 | [Functional Specification](docs/02-Functional-Specification.md) | Per-module behaviour: permissions, fields, validation, workflows, state machines, roll-up, coverage and metric formulas, errors, edge cases, ACs |
| 03 | [HLD](docs/03-HLD.md) | Stack, container and module architecture, data/API/integration architecture, auth, jobs, storage, deployment, security, scalability, observability, config |
| 04 | [LLD](docs/04-LLD.md) | Repository layout, module templates, core primitives, algorithms (versioning, pinning, finalize, transitions, coverage SQL), frontend architecture, conventions |
| 05 | [Database Design](docs/05-Database-Design.md) | Enums, every table and column, constraints, triggers, roles, indexes, ER diagram, migrations, retention, sample records |
| 06 | [API Specification](docs/06-API-Specification.md) | Conventions, error catalog, full endpoint catalog with permissions, key schemas, example flow |
| 07 | [UI/UX Specification](docs/07-UI-UX-Specification.md) | Principles, IA, shell, patterns, 16 screen wireframes, design tokens, states, accessibility, responsive rules, shortcuts |
| 08 | [QA Strategy](docs/08-QA-Strategy.md) | Test levels, CI gates, rule-test design, authz/security/performance/data-integrity testing, UAT, initial test catalog (TCMS-001…143) |
| 09 | [Implementation Roadmap](docs/09-Implementation-Roadmap.md) | MVP milestones M0–M9 with scope/acceptance, technical milestones, Phase 2/3, Definition of Done |
| 10 | [Backlog](docs/10-Backlog.md) | Epics, user stories with priorities, sizes, references and acceptance; technical tasks per epic |
| 11 | [Decision Log](docs/11-Decision-Log.md) | ADR-001…022 with rationale, trade-offs and alternatives |
| 12 | [Glossary](docs/12-Glossary.md) | Terms |
| — | [ops/](docs/ops/) | Step 0 review, local setup, environment variables, migrations, testing, known limitations, implementation checklist |

ID conventions: `FR-<MOD>-nnn` functional requirement · `NFR-<AREA>-nn` · `BR-nn` business rule · `AC-<MOD>-nn` acceptance criterion · `US-nnn` story · `TCMS-nnn` test case · `ADR-nnn` decision.

## Open items (assumptions in effect)

| # | Question | Working assumption | Where it matters |
| --- | --- | --- | --- |
| 1 | Jira Cloud or Data Center? | Jira Cloud | Phase 2 connector auth/API |
| 2 | Source of truth for requirements in Jira-linked projects | Jira for linked projects; TCMS elsewhere | BR-33, Phase 2 |
| 3 | Data-validation case format in MVP? | Phase 2 | SPARK telemetry tests use Steps in MVP |
| 4 | Retention of results and attachments | Results indefinitely; attachments configurable, default indefinite | Retention jobs |
| 5 | Automation frameworks used by SPARK | JUnit XML covers them | Phase 2 parsers |

Decided on 2026-11-04: the Jira connector moves to the start of Phase 2, and MFA is in the MVP (ADR-020).

Changing an assumption: update the affected documents and add an ADR.
