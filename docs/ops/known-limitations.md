# Known limitations

Current as of M1 (2026-11-04). Remove entries when resolved.

| # | Limitation | Impact | Plan |
| --- | --- | --- | --- |
| L1 | Docker Hub, quay.io and Bitnami no longer publish MinIO images; local dev and tests use `cgr.dev/chainguard/minio:latest` (same MinIO server) | `:latest` is the only free Chainguard tag, so the image floats | Pin a digest before staging; production uses any S3-compatible store (ADR-010) |
| L4 | Attachment storage has service primitives but no routes | — | Routes arrive with the first owning entity (M2) |
| L5 | Light theme only (review K16) | No dark mode toggle is rendered | When dark tokens are designed |
| L6 | The "< 10 min" measurement excludes first-time base-image pulls | Depends on network | — |
| L7 | FastAPI's TestClient warns that `httpx` support is deprecated in favour of `httpx2` | Warning only | Switch when the FastAPI test client supports it without warnings |
| L8 | Client IP comes from the TCP peer; behind a reverse proxy every request has the proxy's IP (affects the auth rate limit and session/attempt records) | Production only | M8: run uvicorn/gunicorn with `--forwarded-allow-ips` set to the proxy |
| L9 | The general 600 req/min per-user rate limit (docs/06 §2.10) and `RateLimit-*` headers are not implemented; only the auth limit is | No throttling of authenticated traffic | M8 hardening |
| L10 | `Idempotency-Key` (docs/06 §2.8) is not implemented yet | Duplicate POSTs are not deduplicated | M2, with the first high-volume creates |
| L11 | `GET /projects/{id}/resolve` arrives with the first keyed entity (M2); URLs use the project key and the client resolves it from the project list | — | M2 |
| L12 | Landing page is the last project's Activity (or the project list) until My Work exists | — | M4 |
| L13 | TCMS-002 timing test runs serially (`-m timing`); under heavy parallel load wall-clock comparisons are noisy | — | — |
