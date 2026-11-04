# Known limitations

Current as of M2 (2026-11-05). Remove entries when resolved.

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
| L19 | Requirement filters (`requirement_id`, `has_requirements`), "Add to plan/cycle" and export bulk actions are not built | — | M3 (plans/cycles), M6 (requirements), M8 (export) |
