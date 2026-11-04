# 12 — Glossary

| Term | Definition |
| --- | --- |
| Organization | Tenant; contains users, projects and settings. |
| Project | Testing context with its own key (e.g. `SPARK`), repository, plans, cycles, defects, requirements and reports. |
| Project key | 2–10 character uppercase identifier used in human keys; immutable. |
| Human key | Readable identifier `PROJECT-PREFIX-n` (`SPARK-TC-12`). Prefixes: TC case, PL plan, CY cycle, D defect, R requirement. |
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
| Needs retest | Flag on runs linked to a defect that is Ready for Retest. |
| Pool | Unassigned runs in a cycle that any tester can claim. |
| Defect | A recorded problem with lifecycle; linked to results, cases, requirements. |
| Open defect | Defect in open, triaged, assigned, in_progress, fixed, ready_for_retest or reopened. |
| Requirement | Something the product must do (epic, feature, story, functional/non-functional, business). |
| Coverage | A requirement is covered when at least one active case is linked. |
| Status in release | Requirement status computed from the latest results of its linked cases in a release. |
| RTM | Requirements Traceability Matrix: requirement → cases → latest results → defects. |
| Execution progress | (Passed + Failed + Blocked) ÷ (all runs − Not applicable). |
| Pass rate | Passed ÷ (Passed + Failed + Blocked). |
| Readiness rule | A structured exit criterion evaluated for a release (e.g. no open critical defects). |
| Release decision | Recorded go / go with risks / no-go with snapshot of rules and metrics. |
| Audit event | Immutable record of who changed what, when, with old and new values. |
| Access review | Export of users, roles and MFA status for compliance reviews. |
| Connector | Adapter to an external system (e.g. Jira Cloud) used by the integrations module. |
| External link | Association between a TCMS record and an external record, with an owner and mirrored fields. |
| Automation key | Identifier that maps an automated test result (e.g. JUnit `classname.name`) to a case. |
| Org Admin | Organization administrator; implicit admin on every project. |
| UoW | Unit of Work: one database transaction per request or job, collecting audit, events and jobs. |
| AccessContext | Server-side object carrying the principal, project and effective permissions for a request. |
