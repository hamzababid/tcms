# Accepted security findings

The CI gates fail on known vulnerabilities (docs/08 §4, M8 D14):

| Gate | Scope | Fails on |
| --- | --- | --- |
| `pip-audit` | Backend runtime dependencies (`uv.lock`, no dev group) | Any known vulnerability |
| `pnpm audit` | Frontend production dependencies | High and critical |
| Trivy | `assay-backend` and `assay-web` runtime images | High and critical with a fix available |
| ZAP baseline | Nightly, against the production stack (`deploy/`, Caddy, local drill settings) | Any rule marked FAIL in `security/zap-rules.tsv`; warnings are reported in the artifact only |

A finding that cannot be fixed yet is accepted only with a row below and the matching ignore entry
(`security/trivyignore`, `--ignore-vuln` for pip-audit, `security/zap-rules.tsv`). Remove the row when the
expiry passes or the fix ships.

| ID | Where | Why it is accepted | Owner | Expires |
| --- | --- | --- | --- | --- |
| ZAP 10055 | SPA CSP (`deploy/Caddyfile`) | `style-src 'unsafe-inline'`: Radix and Recharts set inline styles; scripts stay `'self'` only (ASVS V3.4.3, docs/ops/asvs-l2.md) | M9 | 2027-05-01 |
| ZAP 90004 | All responses | No `Cross-Origin-Embedder-Policy`: Assay needs no cross-origin isolation, and `require-corp` would break presigned attachment downloads from external S3. COOP and CORP are set | accept | 2027-05-01 |

## History
- 2026-11-11: the first scheduled nightly failed. It scanned the development stack (the Vite dev server, which
  sends none of the production headers), and `zap-baseline.py` exits 2 on warnings, which the job treated as a
  failure. The nightly now scans the production stack behind Caddy and runs with `-I`, so only FAIL rules fail
  it; the header rules (clickjacking, nosniff, HSTS, CSP, Permissions-Policy, cookie flags) are FAIL. Caddy got
  `default_sni`, because ZAP's Java client sends no SNI for `localhost` and the handshake failed. The first CI run of the new job also showed that `deploy/make-secrets.sh` made the
  secret files 0600, which the non-root containers cannot read on Linux (Docker Desktop on macOS hides this);
  the files are now 0644 inside a 0700 directory. Result: 0 FAIL, 2 accepted warnings (above), 62 rules pass.

- 2026-11-08 (M8c): first scans. Trivy reported 12 high/critical findings in the backend image and 55 in the
  web image, all OS packages with fixes released after the base images were built; both Dockerfiles now
  upgrade packages in the runtime stage. Eight more came from the AlmaLinux 8 libraries vendored by the
  `psycopg-binary` wheel; the runtime image now uses Debian's `libpq5` with plain `psycopg`, and the binary
  wheel stays in the dev group only. pip-audit and pnpm audit found nothing.
