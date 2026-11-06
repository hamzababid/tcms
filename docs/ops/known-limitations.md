# Known limitations

Current as of M3 (2026-11-05). Remove entries when resolved.

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
| L15 | Bulk actions over 200 cases run as a job, but the UI does not report completion; the list refreshes on the next load | User refreshes to see the result | M7 notification bell / job progress |
| L16 | Notifications (review requested, returned, approved, mentions) are stored but there is no notification bell yet | Not visible in the UI | M7 |
| L18 | Attachments and pasted images need a saved case (the upload targets its ID); the new-case editor says so | One extra step for new cases | — |
| L19 | Requirement filters (`requirement_id`, `has_requirements`) and the export bulk action are not built. "Add to plan" / "Add to cycle" work on selected cases, not on "Select all matching" | — | M6 (requirements), M8 (export) |
| L20 | The design's topbar search, notification bell and "Keyboard shortcuts" footer (docs/design/Topbar, Sidebar) are not rendered until those features exist (no dummy controls) | — | Global search and shortcut help: M8; notifications: M7 |
| L24 | The new-cycle dialog shows "added N · skipped M" with reasons **after** creating, not the "will add N, skip M" preview of docs/07 §5.8 (docs/06 has no dry-run endpoint) | One extra look after creating | Add a dry-run to docs/06 if the preview is wanted |
| L25 | Plan detail has no **Requirements** tab and the "Add cases" dialog has no **Saved view** tab (`saved_view_id` → 422); the plan Overview lists exit rules but not their readiness | — | M6 (requirements, saved views), M7 (readiness) |
| L26 | Cycle runs have no export (the Bugs column arrived in M5) | — | M8 (export) |
| L27 | Runs are reordered with "Sort runs by folder / priority"; drag-and-drop reordering (`run_ids_in_order` is supported by the API) is not in the UI | — | When asked for |
| L29 | Evidence attaches to a step (`test_step_result`) only; attempt-level attachments (`test_result`) are not offered in the runner | Text-format cases have no evidence upload | When asked for |
| L30 | The sidebar does not collapse automatically in the runner (docs/design/Runner) | Less room for the step grid on small screens | When asked for |
| L31 | The 50-tester save target (AC-EXE-09) is checked by a timing test, not a load test on the TM-4 seed | — | M8 (k6) |
| L32 | Assay does not read bug status from the tracker (ADR-023): "Ready for retest" is a manual action by a QA Lead or Manager, and the readiness rule counts failed runs, not open bugs | A fixed bug needs one click in Assay to flag its runs | Phase 2 tracker connector (FR-DEF-007) |
| L33 | Bug links have no notifications (a linked run being flagged for retest does not notify the tester yet) | Testers see ⟳ in My Work and the cycle | M7 notification bell |
| L34 | Requirement-level bug links are derived from case links only; the Traceability view that shows them arrives with requirements | — | M6 |
| L35 | The unused baseline defect tables (`defects`, `defect_links`, `defect_status_history`, `defect_watchers`) and the `defect.transition.*` permissions stay in the schema | No effect on users | Drop or reuse with the tracker connector |
| L36 | Two simultaneous project creations with the same name return 500 instead of `409 name_taken` (race between the name check and the insert) | Rare; seen only in parallel E2E | Map the unique violation to 409 |
