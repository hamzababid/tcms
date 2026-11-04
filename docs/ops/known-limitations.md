# Known limitations

Current as of M0 (2026-11-04). Remove entries when resolved.

| # | Limitation | Impact | Plan |
| --- | --- | --- | --- |
| L1 | Docker Hub, quay.io and Bitnami no longer publish MinIO images; local dev and tests use `cgr.dev/chainguard/minio:latest` (same MinIO server) | `:latest` is the only free Chainguard tag, so the image floats | Pin a digest before staging; production uses any S3-compatible store (ADR-010) |
| L2 | No application features yet: no sign-in, no projects | The web app shows only the shell | M1 |
| L3 | `make seed` has no steps in M0 (system roles come from the migration) | Nothing to explore yet | M1 adds org, users per role and SPARK |
| L4 | Attachment storage has service primitives but no routes | — | Routes arrive with the first owning entity (M2) |
| L5 | Light theme only (review K16) | No dark mode toggle is rendered | When dark tokens are designed |
| L6 | The "< 10 min" measurement excludes first-time base-image pulls | Depends on network | — |
| L7 | FastAPI's TestClient warns that `httpx` support is deprecated in favour of `httpx2` | Warning only | Switch when the FastAPI test client supports it without warnings |
