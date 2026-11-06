# 12 — Glossary

| Term | Definition |
| --- | --- |
| Organization | Tenant; contains users, projects and settings. |
| Project | Testing context with its own key (e.g. `SPARK`), repository, plans, cycles, bug links, requirements and reports. |
| Project key | 2–10 character uppercase identifier used in human keys; immutable. |
| Human key | Readable identifier `PROJECT-PREFIX-n` (`SPARK-TC-12`). Prefixes: TC case, PL plan, CY cycle (D and R reserved; bugs and requirements use the team's own keys). |
| Release | A version or milestone of the product under test (e.g. SPARK v2.5); anchors plans, cycles, readiness and coverage. |
| Environment | Where testing happens (QA, Staging, UAT). Each cycle runs in exactly one environment (MVP). |
| Repository | The project's library of test cases organized in folders. |
| Folder | A node in the repository tree; also called suite. Each case has one home folder. |
| Module | The folder at the project's configured "module depth"; used for report grouping. |
| Test case | Reusable, versioned description of a test, independent of any cycle. |
| Version | Immutable snapshot of a case's content, numbered 1, 2, 3… |
| Content vs metadata | Content fields (title, steps, preconditions…) create versions; metadata (folder, priority, tags, owner…) does not. |
| Format | How a case's procedure is expressed: Steps or Text (P2: Exploratory, Data validation; P3: BDD). |
| Approved version | The version cycles use when approval is enforced. |
| Test plan | Scope and strategy for a release or purpose; selects cases and requirements; generates cycles. |
| Cycle | An execution effort (e.g. "Regression Cycle 01") in one environment, containing runs. |
| Run | One case in one cycle, pinned to one case version; has an assignee and a derived status. |
| Attempt (result) | One execution of a run. Draft while being executed; final and immutable once finished. |
| Step result | Status, actual result and evidence for one step within an attempt. |
| Retest | A new attempt on a run that already has a final attempt. |
| Correction | A new attempt that explicitly corrects an earlier final attempt, with a reason. |
| Superseded run | A run replaced by a new run at a newer version; kept for history, excluded from metrics. |
| Needs retest | Flag on runs linked to a bug reference marked Ready for retest. |
| Pool | Unassigned runs in a cycle that any tester can claim. |
| Bug link | A reference (with optional URL and title) to a bug in the team's tracker, attached to an attempt or a case (ADR-023). |
| Requirement reference | The team's identifier for a requirement or story in its own tool (`SPK-120`), with an optional link and title; linked to cases and plans (ADR-024). |
| Coverage | A requirement reference is covered when at least one active case is linked. |
| Status in release | Requirement status computed from the latest results of its linked cases in a release. |
| RTM | Requirements Traceability Matrix: requirement reference → cases → latest results → linked bugs. |
| Execution progress | (Passed + Failed + Blocked) ÷ (all runs − Not applicable). |
| Pass rate | Passed ÷ (Passed + Failed + Blocked). |
| Readiness rule | A structured exit criterion evaluated for a release (e.g. no failed runs). |
| Release decision | Recorded go / go with risks / no-go with snapshot of rules and metrics. |
| Audit event | Immutable record of who changed what, when, with old and new values. |
| Access review | Export of users, roles and MFA status for compliance reviews. |
| Connector | Adapter to an external system (e.g. Jira Cloud) used by the integrations module. |
| External link | Association between a TCMS record and an external record, with an owner and mirrored fields. |
| Automation key | Identifier that maps an automated test result (e.g. JUnit `classname.name`) to a case. |
| Org Admin | Organization administrator; implicit admin on every project. |
| UoW | Unit of Work: one database transaction per request or job, collecting audit, events and jobs. |
| AccessContext | Server-side object carrying the principal, project and effective permissions for a request. |
