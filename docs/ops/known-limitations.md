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
| L12 | Landing page is the last project's Activity (or the project list) until My Work exists | — | M4 |
| L13 | TCMS-002 timing test runs serially (`-m timing`); under heavy parallel load wall-clock comparisons are noisy | — | — |
| L14 | Repository tree speed (US-043: 2,000 folders < 1 s) and "counts may be cached for > 500 folders" are not measured or cached yet; counts are computed per request | Large trees untested | M4 large seed (TM-4) |
| L15 | Bulk actions over 200 cases run as a job, but the UI does not report completion; the list refreshes on the next load | User refreshes to see the result | M7 notification bell / job progress |
| L16 | Notifications (review requested, returned, approved, mentions) are stored but there is no notification bell yet | Not visible in the UI | M7 |
| L18 | Attachments and pasted images need a saved case (the upload targets its ID); the new-case editor says so | One extra step for new cases | — |
| L19 | Requirement filters (`requirement_id`, `has_requirements`) and the export bulk action are not built. "Add to plan" / "Add to cycle" work on selected cases, not on "Select all matching" | — | M6 (requirements), M8 (export) |
| L20 | The design's topbar search, notification bell and "Keyboard shortcuts" footer (docs/design/Topbar, Sidebar) are not rendered until those features exist (no dummy controls) | — | Global search and shortcut help: M8; notifications: M7 |
| L21 | **Replace run (BR-05)** is built and API-tested (`test_br_05_replace_run_supersedes`) and offered in the run panel, but its retest-round **E2E is deferred**: a run only has results once the runner exists (M3 decision Q5) | No browser test of replace yet | M4: add the E2E with the runner |
| L22 | Draft attempts come from the runner, so **closing a cycle with drafts** (409 `draft_exists` → list → discard) is covered by API tests only (`test_tcms_058_close_lists_drafts_and_discard_removes_them`); the M3 E2E closes a cycle without drafts | — | M4: E2E with a live draft |
| L23 | A cycle starts with **Start cycle**; the automatic start on the first execution (BR-30) needs the runner. "Start testing" (runner queue) is not rendered | — | M4 |
| L24 | The new-cycle dialog shows "added N · skipped M" with reasons **after** creating, not the "will add N, skip M" preview of docs/07 §5.8 (docs/06 has no dry-run endpoint) | One extra look after creating | Add a dry-run to docs/06 if the preview is wanted |
| L25 | Plan detail has no **Requirements** tab and the "Add cases" dialog has no **Saved view** tab (`saved_view_id` → 422); the plan Overview lists exit rules but not their readiness | — | M6 (requirements, saved views), M7 (readiness) |
| L26 | Cycle runs have no **Defects** column and no export | — | M5 (defects), M8 (export) |
| L27 | Runs are reordered with "Sort runs by folder / priority"; drag-and-drop reordering (`run_ids_in_order` is supported by the API) is not in the UI | — | When asked for |
