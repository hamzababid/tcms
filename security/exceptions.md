# Accepted security findings

The CI gates fail on known vulnerabilities (docs/08 §4, M8 D14):

| Gate | Scope | Fails on |
| --- | --- | --- |
| `pip-audit` | Backend runtime dependencies (`uv.lock`, no dev group) | Any known vulnerability |
| `pnpm audit` | Frontend production dependencies | High and critical |
| Trivy | `assay-backend` and `assay-web` runtime images | High and critical with a fix available |
| ZAP baseline | Nightly, against the CI stack | Any "FAIL" rule (`security/zap-rules.tsv`) |

A finding that cannot be fixed yet is accepted only with a row below and the matching ignore entry
(`security/trivyignore`, `--ignore-vuln` for pip-audit, `security/zap-rules.tsv`). Remove the row when the
expiry passes or the fix ships.

| ID | Where | Why it is accepted | Owner | Expires |
| --- | --- | --- | --- | --- |
| — | — | No accepted findings (2026-11-08) | — | — |

## History

- 2026-11-08 (M8c): first scans. Trivy reported 12 high/critical findings in the backend image and 55 in the
  web image, all OS packages with fixes released after the base images were built; both Dockerfiles now
  upgrade packages in the runtime stage. Eight more came from the AlmaLinux 8 libraries vendored by the
  `psycopg-binary` wheel; the runtime image now uses Debian's `libpq5` with plain `psycopg`, and the binary
  wheel stays in the dev group only. pip-audit and pnpm audit found nothing.
