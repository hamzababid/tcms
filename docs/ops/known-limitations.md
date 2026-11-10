# Known limitations

Current as of M8c (2026-11-10). Remove entries when resolved.

Resolved in M8c: L1 (MinIO and the other third-party production images pinned by digest; development and tests use the same MinIO digest), L8 (client IP from Caddy's `X-Forwarded-For`), L9 (general rate limit and `RateLimit-*` headers), L14 (tree with 2,000 folders: p95 93 ms), L20 (`?` shortcut help and the sidebar entry), L31 (k6 P2 with 50 testers), L36 (project-name race → 409), L43 (`xlarge` seed with 100,000 cases and 500,000 runs).

| # | Limitation | Impact | Plan |
| --- | --- | --- | --- |
| L5 | Light theme only (review K16) | No dark mode toggle is rendered | When dark tokens are designed |
| L6 | The "< 10 min" measurement excludes first-time base-image pulls | Depends on network | — |
| L7 | FastAPI's TestClient warns that `httpx` support is deprecated in favour of `httpx2` | Warning only | Switch when the FastAPI test client supports it without warnings |
| L13 | TCMS-002 timing test runs serially (`-m timing`); under heavy parallel load wall-clock comparisons are noisy | — | — |
| L18 | Attachments and pasted images need a saved case (the upload targets its ID); the new-case editor says so | One extra step for new cases | — |
| L19 | "Add to plan" / "Add to cycle" work on selected cases, not on "Select all matching" (Export does since M8a) | — | When asked for |
| L24 | The new-cycle dialog shows "added N · skipped M" with reasons **after** creating, not the "will add N, skip M" preview of docs/07 §5.8 (docs/06 has no dry-run endpoint) | One extra look after creating | Add a dry-run to docs/06 if the preview is wanted |
| L27 | Runs are reordered with "Sort runs by folder / priority"; drag-and-drop reordering (`run_ids_in_order` is supported by the API) is not in the UI | — | When asked for |
| L29 | Evidence attaches to a step (`test_step_result`) only; attempt-level attachments (`test_result`) are not offered in the runner | Text-format cases have no evidence upload | When asked for |
| L30 | The sidebar does not collapse automatically in the runner (docs/design/Runner) | Less room for the step grid on small screens | When asked for |
| L32 | Assay does not read bug status from the tracker (ADR-023): "Ready for retest" is a manual action by a QA Lead or Manager, and the readiness rule counts failed runs, not open bugs | A fixed bug needs one click in Assay to flag its runs | Phase 2 tracker connector (FR-DEF-007) |
| L35 | The unused baseline defect tables (`defects`, `defect_links`, `defect_status_history`, `defect_watchers`) and the `defect.transition.*` permissions stay in the schema | No effect on users | Drop or reuse with the tracker connector |
| L37 | Assay does not read requirement titles or status from the team's tool (ADR-024); the title is a label typed or pasted in Assay | A renamed story keeps its old title until edited | Phase 2 requirements connector |
| L39 | The filter operators "is not" and "is empty" (docs/02 §12) are not offered on every list | Some negative filters need a saved view or the API | When asked for |
| L40 | Saved views store filters, sort and screen state, not column visibility (which stays per browser) | Shared views open with the reader's own columns | When asked for |
| L41 | Cycle "Add cases" has no Saved view tab (`saved_view_id` works for plans only) | Use the folder or filter tab | When asked for |
| L42 | Global search covers the projects the user is a member of; an Org Admin sees other projects only when searching inside one | — | — |
| L44 | Snapshots of past days report runs without a final attempt as "not run"; "in progress" exists only live | Trend lines show no in-progress band | — |
| L45 | The Overview offers Release, Environment and Tester filters; the API also takes cycles, module and a date range, which the screen does not offer yet | Use Reports for those filters | When asked for |
| L46 | The Releases page evaluates readiness for planned and active releases only; released and archived releases show their last decision | — | — |
| L48 | The bell refreshes its count every 60 s and on window focus; there is no push channel | A new notification can take up to a minute to show | Server-sent events if asked for |
| L49 | The bell lists the latest 20 notifications; there is no full notification history page | Older ones stay in the database for 180 days but are not browsable | When asked for |
| L50 | Email covers mentions and the daily assignment digest only (docs/02 §2.7); reviews, retests and exports are in-app only | — | — |
| L51 | Import covers case content, metadata, folders, tags and steps, and requirement references with case links. Attachments, comments, case links and automation keys are not imported, and the export does not include them | Move those by hand after an import | When asked for |
| L52 | Value mapping in the wizard is offered for columns with 30 distinct values or fewer; other columns rely on the built-in synonyms ("P1" → high and so on) | An unusual value in a wide column is reported as `invalid_value` and needs fixing in the file | When asked for |
| L53 | An import commits in one transaction: 5,000 cases with 20,000 steps take about 41 s, and the project's case key sequence row stays locked until the import commits | Creating a case in that project waits for the import to finish | Within US-150's 2-minute target; revisit if larger files are needed |
| L54 | Administration › System retries failed jobs but has no "discard" (docs/07 §5.13); a failed job stays listed until the 90-day job clean-up deletes it | A job that cannot succeed stays in the list | Add discard if the list gets noisy |
| L55 | Installation jobs (no organization, e.g. the daily clean-ups) are listed and retryable by the administrators of every organization on the installation | Only matters for multi-organization installations; payloads are never shown | Restrict to an installation operator role if multi-tenant hosting is offered |
| L56 | The audit log and access review CSV/XLSX are built in the request: the audit CSV stops at 100,000 events (`422 too_many_rows`), with no background export | Very wide date ranges need narrower filters | Move to the background export path if needed |
| L57 | The quality dashboard's live "today" counters and its release table are cached for up to 5 minutes in each API process (docs/04 §8) | A result recorded a moment ago can take up to 5 minutes to show there; the manager dashboard, cycles and runs are live | Shorter TTL or invalidation on finish if users notice |
| L58 | The general rate limit (600/min per caller) is counted in each API process, without a shared store | With N replicas a caller can make up to N × 600 requests a minute | Shared store (Redis or PostgreSQL) if abuse is seen (ADR-005 trigger) |
| L59 | Under 50 concurrent testers (k6 P2, laptop) starting an attempt takes p95 1.17 s and finishing p95 558 ms; step saves meet their 200 ms target | Start and finish feel slower than other actions at peak | Profile on the pilot host in M9 |
| L60 | Load tests ran on a 12-core laptop with 8 API replicas, not on the 4 vCPU / 8 GB host of docs/01 §8.2; under the P4 mix (50 VUs) the case list reached p95 538 ms and the manager dashboard p95 9.8 s | Production sizing is not proven | M9: rerun P1–P6 on the pilot host and size `API_REPLICAS` and PostgreSQL from it |
| L61 | ASVS L2 review: 40 requirements partial and 14 not met, each with an owner in docs/ops/asvs-l2.md (for example `__Host-` cookie prefixes, MinIO root credentials used by the app, tokens in reset/invitation URLs, no unpacked-size limit for XLSX imports, security events not logged); the authenticated ZAP scan covered the API only | See the checklist | M9 items before go-live; the rest Phase 2 or accepted |
