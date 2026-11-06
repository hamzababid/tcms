# M7 — Reporting, readiness and notifications · Requirements

| Field | Value |
| --- | --- |
| Milestone | M7 (docs/09 §2): "Managers can assess and record release readiness" |
| Epics | E13 Dashboards, reports, readiness (US-140…146); E16 Notifications and email (US-170, US-171) |
| Adapted to | ADR-023 (bugs are links to the team's tracker: no severity, no open/resolved counts) and ADR-024 (requirements are references) |
| Carried from earlier | L15 (bulk job completion), L16 + L20 (notification bell), L25 (plan readiness on the Overview), L26 (cycle runs export → cycle execution report), L33 (Ready for retest notifies the tester), L38 (traceability export → traceability report) |
| Out of scope | PDF reports, first-time pass rate, tester throughput, failure hotspots (P2.6); list exports of cases/requirements/bug links and the import wizard (M8); k6 load runs (M8); reading bug or requirement status from a tool (P2) |

## Business rules

- **BR-24** — Metrics follow docs/02 §11.2 exactly. Superseded runs are always excluded; Not applicable runs are shown but left out of denominators; a rate with a zero denominator is `null` and shown as "—"; every rate carries numerator and denominator.
- **BR-26 (family)** — Release decisions are append-only; the stored snapshot never changes.
- **New** — A readiness rule whose actual value is undefined (zero denominator, or no runs in scope) is **not met**.

## AC (new; docs/02 §11 has none)

- **AC-RPT-01** — Given a cycle with 10 runs (6 P, 2 F, 1 B, 1 NA) and one superseded failed run, then the summary is total 10, applicable 9, executed 9, pass rate 6 of 9, execution progress 9 of 9; the superseded run is not counted (TCMS-113/114).
- **AC-RPT-02** — Given a cycle with no executed runs, then pass rate is `null` (shown "—"), not 0% (TCMS-113).
- **AC-RPT-03** — The numbers on the Overview (execution, bugs, coverage, team) equal the numbers of the matching report with the same filters (TCMS-115).
- **AC-RPT-04** — Given a report with ≤ 10,000 rows, export returns the file at once; above, it returns `202 {transfer_id}`, the file is ready later, the initiator is notified and the file expires after 7 days.
- **AC-RPT-05** — Given a cell value starting with `=`, `+`, `-`, `@`, tab or carriage return, then CSV and XLSX exports write it prefixed with `'` (TCMS-117).
- **AC-REL-01** — Given plan rules `min_pass_rate ≥ 95%` and `max_failed = 0` and results 180 P / 20 F, then readiness shows both rules not met with actual values and counts, and the release is Not ready (TCMS-116).
- **AC-REL-02** — Given a release whose plans have no exit rules, then the default rules apply (progress 100%, no failed runs, pass rate of applicable ≥ 95%, requirement coverage ≥ 90%).
- **AC-REL-03** — When the QA Manager records "Go with risks" without risks, then `422`; with risks, the decision is stored with a snapshot of every rule result and metric; later results do not change the stored snapshot; UPDATE/DELETE on the row fail (TCMS-116).
- **AC-NTF-01** — Given runs assigned to Sana, then Sana's bell shows the unread count; opening a notification marks it read; "Mark all read" clears the count.
- **AC-NTF-02** — Given Sana opted out of mention emails, when she is mentioned, then she gets the in-app notification and no email.
- **AC-NTF-03** — Given runs assigned to Sana yesterday, then one digest email reaches her at 07:00 in her time zone, listing them; no digest is sent when nothing is new or she opted out.

## Tests (docs/08 §15)

| ID | Test | Level |
| --- | --- | --- |
| TCMS-113 | Execution summary rates and undefined denominators (AC-RPT-01/02) | Unit + property test vs oracle |
| TCMS-114 | Superseded runs excluded from every metric | API + property test |
| TCMS-115 | Overview widgets agree with the reports | API + E2E |
| TCMS-116 | Readiness evaluates rules; decision stored immutable (AC-REL-01…03) | Unit + API |
| TCMS-117 | Cycle execution XLSX/CSV export with formula-injection protection (AC-RPT-05) | API |
| new | Notifications: bell, read, mark all, opt-outs, digest (AC-NTF-01…03) | API + E2E |
| new | Dashboards < 2 s on the large seed | Timing (local, logged) |

---

### R-140 · One metrics module (US-140)
`reporting/metrics.py` stays the only place that defines metrics. Add the §11.2 metrics it lacks: retest count, failures without a bug, linked bugs (distinct references), total active cases, automation coverage. One SQL module (`reporting/queries.py`) counts runs for any filter: release, cycles, environment, module (folder at `report_module_depth`), tester, date range (attempt `finished_at`). Every screen and export goes through it.

### R-141 · Project Overview = QA Manager dashboard (US-141)
`/p/:key` (today it redirects to Activity) per docs/07 §5.3 and docs/02 §11.3: readiness, execution summary, bugs (linked; on failing runs; failures without a bug), active cycles with progress bars and overdue flag, status breakdown per cycle, requirement coverage with top 10 uncovered, regression status, team progress (per tester: assigned, executed, remaining, failed, blocked), repository. Filters: release, cycles, environment, module, tester, date range; the last filter is remembered per user. Each widget links to the detailed view with the filter applied. < 2 s.

### R-142 · My Work for engineers (US-142)
Add to My Work: executed today / this week, my failed and blocked runs awaiting retest, bugs I linked, upcoming cycles (start in the next 14 days) where I have runs.

### R-143 · Quality trends (US-143)
Nightly job writes `metric_snapshots` per project × release and per cycle × day; today is computed live; "Refresh" enqueues today's snapshot (1 per 10 min). Quality dashboard (Reports › Quality): execution and pass rate per day, P/F/B per day, bug links per day, bugs by module, coverage per release, automation coverage, regression status, release-wise quality for the last 6 releases. Every chart has a data table toggle.

### R-144 · Six reports and export (US-144)
Cycle execution, results history, bug links, traceability, tester activity, test case inventory (columns in design D9). Filterable, paginated tables; CSV and XLSX export with `data.export`; sync ≤ 10,000 rows, else a background job (≤ 500,000 rows), notify on completion, keep 7 days.

### R-145 · Release readiness and decision (US-145)
Releases list and a release page (`/p/:key/releases/:id`) with tabs Readiness, Plans, Cycles, Bugs, Decisions. Readiness shows each rule (threshold, actual with counts, met), the plan it comes from, and Ready / Not ready. "Record decision" (`release.manage`): Go, Go with risks (risks required), No-go; comment required; snapshot stored; timeline with snapshot viewer. The plan Overview shows the plan's rules as met / not met (L25).

### R-146 · Organization dashboard (US-146)
`/org`: one row per project: active cycles, execution progress, pass rate, failed runs, bugs on failing runs, last activity. Org Admins see every project; others see their projects.

### R-170 · In-app notifications (US-170)
Bell in the top bar with unread count; list (latest 20, "Show all"), open = go to the item and mark read, "Mark all read". Events: runs assigned, case submitted / approved / returned, mentioned, bulk action finished (L15), export ready, runs flagged Ready for retest (to the run assignee, L33). Notifications older than 180 days are purged.

### R-171 · Email (US-171)
Mention email right away; daily digest of newly assigned runs at 07:00 in the user's time zone. Both can be switched off in Profile › Notifications. Templates in text and HTML with the brand header.
