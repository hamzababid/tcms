# M5 — Bug links · Requirements

| Field | Value |
| --- | --- |
| Milestone | M5 (docs/09 §2), re-scoped on 2026-11-06 by the product owner: bugs live in each team's own tracker (Jira, Azure DevOps, GitHub, Linear, …); Assay records **links** to them. No defect workflow inside Assay |
| Epic | E10 Defects → **Bug links** (docs/10 rewritten) |
| Replaces | US-110…US-117 (internal defects, state machine, kanban, watchers), BR-19, BR-22, FR-DEF-001…007; see ADR in docs/11 |
| Carried from M4 | L26 (cycle runs column), L28 (`require_defect_for_failure`, runner action, My Work block) |
| Out of scope | Reading bug status from a tracker (a future connector, P2); notifications for bugs; export (M8) |

## Concept

A **bug link** is a reference to a bug in an external tracker: a `reference` (what the team calls it, e.g. `SPK-431`, `#1287`, `AB#5521`), an optional `url`, and an optional `title`. It is attached to a failed (or any) step / attempt of a run, or directly to a test case. The same reference may be linked from many runs and cases; Assay groups them by reference. Assay never stores the bug's status, assignee or workflow.

## Business rules (rewritten)

- **BR-19** — *(retired: no internal defect state machine.)*
- **BR-20** — A bug link created from a result records that attempt, its run, the step (if any) and the case. Links are not part of the attempt: they can be added to and removed from draft and finalized attempts, so BR-06 is unaffected.
- **BR-21** — "Ready for retest" on a bug reference sets `needs_retest = true` on every non-superseded run linked to that reference in a non-closed cycle; a new finalized attempt on that run clears it (M4).
- **BR-22** — *(retired: there is no defect status to verify.)*
- **New project setting** `require_bug_link_for_failure` (replaces `require_defect_for_failure`): finalizing a Failed attempt with no bug link on that attempt → `422 bug_link_required`.

## AC

- **AC-BUG-01** — Given a failed step 3 of a draft, when the tester links `SPK-431`, then the link stores the attempt, run, step and case, and the run, the cycle runs list and the case show the chip `SPK-431`.
- **AC-BUG-02** — Given the project URL template `https://acme.atlassian.net/browse/{ref}`, when a link is added with reference `SPK-431` and no URL, then its URL is `https://acme.atlassian.net/browse/SPK-431`. A pasted URL is kept as given.
- **AC-BUG-03** — Given `SPK-431` linked to two runs in an active cycle, one superseded run and one run in a closed cycle, when "Ready for retest" is used on `SPK-431`, then only the two active runs get `needs_retest`.
- **AC-BUG-04** — Given `require_bug_link_for_failure`, when a Failed attempt without a bug link is finalized, then `422 bug_link_required`; after linking a bug it finalizes.
- **AC-BUG-05** — Given a URL that is not `http(s)://`, then `422 validation_error` (no `javascript:` or other schemes are stored or rendered).
- **AC-BUG-06** — Given `SPK-431` already linked to an attempt, when it is linked again to the same attempt, then `409 already_linked`.

## Tests (docs/08 §15.6 rewritten)

| ID | Test | Level |
| --- | --- | --- |
| TCMS-100 | Link a bug from a failed step in the runner (keyboard `D`) | E2E (+ API) |
| TCMS-101 | Link validation: reference, URL scheme, template, duplicates (AC-BUG-02/05/06) | Unit + API |
| TCMS-102 | Link a bug to a case directly; it shows on the case | API (+ E2E) |
| TCMS-103 | Ready for retest flags only eligible linked runs (AC-BUG-03, BR-21) | Integration |
| TCMS-104 | Retest clears the flag; the bug chip stays on the run history | E2E |
| TCMS-105 | Same reference from many runs groups in the Bugs list | API |
| TCMS-106 | `require_bug_link_for_failure` (AC-BUG-04) | API + E2E |
| TCMS-107 | Remove a link: creator or manager only; audited | API |

---

### R-110 · Link a bug from the runner
**Refs:** BR-20, NFR-UX-02 · **Tests:** TCMS-100, AC-BUG-01

On each step: "Link bug (D)". A small popover asks for reference (required), URL (optional, filled from the project template) and title (optional); recent references used in this cycle are suggested. Save adds the chip on the step; focus returns to the step; at most 3 interactions. A "Copy bug details" button copies a ready-to-paste bug report (case, steps 1..n of the pinned version, expected, actual, environment, build, cycle, link to the run) for pasting into the team's tracker. Also available for text-format cases and on the attempt (no step).

### R-111 · Link a bug to a case
**Tests:** TCMS-102

Case page: "Bugs" tab lists every link of the case (direct and through runs) with cycle, attempt and step; "Link bug" adds a direct case link (bugs found outside execution).

### R-112 · Where bug links show
- Runner: chips per step and a footer line "Bugs: SPK-431, SPK-440".
- Run panel and run history: chips per attempt.
- Cycle detail: "Bugs" column in the runs table (L26).
- Case page: Bugs tab (R-111).
- Traceability (M6) and reports (M7) read the same links.
Every chip opens the URL in a new tab (`rel="noopener noreferrer"`); a reference without URL is plain text.

### R-113 · Bugs list per project
**Tests:** TCMS-105

`Bugs` page in the project: one row per reference with title, linked cases count, linked runs count, runs currently failed, cycles, first and last linked, and actions "Ready for retest" and "Open in tracker". Filters: cycle, text (reference or title), "linked to failing runs". Selecting a row lists its links.

### R-114 · Ready for retest
**Refs:** BR-21 · **Tests:** TCMS-103, TCMS-104, AC-BUG-03

From the Bugs list or any chip menu: "Ready for retest" (needs `cycle.manage`) flags the eligible linked runs and reports how many; audit `bug.retest_requested`. Cycle detail shows "⟳ n need retest" and the Needs retest filter.

### R-115 · Require a bug link for failures
**Tests:** TCMS-106, AC-BUG-04

Project setting (Options): "A failed result needs a bug link". When on, Finish on a failed attempt without a link opens the link popover instead of failing.

### R-116 · Project bug tracker settings
**Tests:** TCMS-101

Project settings › Options: tracker name (e.g. "Jira", shown on buttons as "Open in Jira"; default "tracker") and URL template with `{ref}` (optional, `http(s)` only). Audited as `project.settings_changed`.

### R-117 · Remove and edit links
**Tests:** TCMS-107

The creator of a link or a user with `defect.edit` may remove it or correct its URL/title; audit `bug.linked`, `bug.updated`, `bug.unlinked`. Discarding a draft removes its attempt links (audited).

### R-118 · My Work and seed
- My Work keeps its three blocks; the planned "Defects assigned to me" block is dropped (assignment lives in the tracker).
- Seed: SPARK project tracker "Jira" with template `https://acme.atlassian.net/browse/{ref}`; `SPK-431` linked to the seeded failed result on SPARK-CY-1; one direct case link.
