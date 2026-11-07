# Known limitations

Current as of M8b (2026-11-07). Remove entries when resolved.

| # | Limitation | Impact | Plan |
| --- | --- | --- | --- |
| L1 | Docker Hub, quay.io and Bitnami no longer publish MinIO images; local dev and tests use `cgr.dev/chainguard/minio:latest` (same MinIO server) | `:latest` is the only free Chainguard tag, so the image floats | Pin a digest before staging; production uses any S3-compatible store (ADR-010) |
| L5 | Light theme only (review K16) | No dark mode toggle is rendered | When dark tokens are designed |
| L6 | The "< 10 min" measurement excludes first-time base-image pulls | Depends on network | — |
| L7 | FastAPI's TestClient warns that `httpx` support is deprecated in favour of `httpx2` | Warning only | Switch when the FastAPI test client supports it without warnings |
| L8 | Client IP comes from the TCP peer; behind a reverse proxy every request has the proxy's IP (affects the auth rate limit and session/attempt records) | Production only | M8: run uvicorn/gunicorn with `--forwarded-allow-ips` set to the proxy |
| L9 | The general 600 req/min per-user rate limit (docs/06 §2.10) and `RateLimit-*` headers are not implemented; only the auth limit is | No throttling of authenticated traffic | M8 hardening |
| L13 | TCMS-002 timing test runs serially (`-m timing`); under heavy parallel load wall-clock comparisons are noisy | — | — |
| L14 | Repository tree speed (US-043: 2,000 folders < 1 s) and "counts may be cached for > 500 folders" are not measured or cached yet; counts are computed per request | Large trees untested | M8 large seed (TM-4) and k6 run; AC-EXE-09 (step saves) is covered by `test_ac_exe_09_…` meanwhile |
| L18 | Attachments and pasted images need a saved case (the upload targets its ID); the new-case editor says so | One extra step for new cases | — |
| L19 | "Add to plan" / "Add to cycle" work on selected cases, not on "Select all matching" (Export does since M8a) | — | When asked for |
| L20 | The design's "Keyboard shortcuts" footer (docs/design/Sidebar) and the `?` shortcut help are not rendered yet (the notification bell arrived in M7, global search in M6) | — | M8 |
| L24 | The new-cycle dialog shows "added N · skipped M" with reasons **after** creating, not the "will add N, skip M" preview of docs/07 §5.8 (docs/06 has no dry-run endpoint) | One extra look after creating | Add a dry-run to docs/06 if the preview is wanted |
| L27 | Runs are reordered with "Sort runs by folder / priority"; drag-and-drop reordering (`run_ids_in_order` is supported by the API) is not in the UI | — | When asked for |
| L29 | Evidence attaches to a step (`test_step_result`) only; attempt-level attachments (`test_result`) are not offered in the runner | Text-format cases have no evidence upload | When asked for |
| L30 | The sidebar does not collapse automatically in the runner (docs/design/Runner) | Less room for the step grid on small screens | When asked for |
| L31 | The 50-tester save target (AC-EXE-09) is checked by a timing test, not a load test on the TM-4 seed | — | M8 (k6) |
| L32 | Assay does not read bug status from the tracker (ADR-023): "Ready for retest" is a manual action by a QA Lead or Manager, and the readiness rule counts failed runs, not open bugs | A fixed bug needs one click in Assay to flag its runs | Phase 2 tracker connector (FR-DEF-007) |
| L35 | The unused baseline defect tables (`defects`, `defect_links`, `defect_status_history`, `defect_watchers`) and the `defect.transition.*` permissions stay in the schema | No effect on users | Drop or reuse with the tracker connector |
| L36 | Two simultaneous project creations with the same name return 500 instead of `409 name_taken` (race between the name check and the insert) | Rare; seen only in parallel E2E | Map the unique violation to 409 |
| L37 | Assay does not read requirement titles or status from the team's tool (ADR-024); the title is a label typed or pasted in Assay | A renamed story keeps its old title until edited | Phase 2 requirements connector |
| L39 | The filter operators "is not" and "is empty" (docs/02 §12) are not offered on every list | Some negative filters need a saved view or the API | When asked for |
| L40 | Saved views store filters, sort and screen state, not column visibility (which stays per browser) | Shared views open with the reader's own columns | When asked for |
| L41 | Cycle "Add cases" has no Saved view tab (`saved_view_id` works for plans only) | Use the folder or filter tab | When asked for |
| L42 | Global search covers the projects the user is a member of; an Org Admin sees other projects only when searching inside one | — | — |
| L43 | The `large` seed loads twice the year-one volume (20,000 cases, 100,000 runs) instead of the 10× set of docs/08 §3 (100,000 cases, 500,000 attempts): the bulk insert of 500,000 runs did not finish in 18 minutes | Dashboard timings in docs/ops/performance.md are measured at 2× year one | M8: faster loader (COPY, deferred indexes) for the k6 run |
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
