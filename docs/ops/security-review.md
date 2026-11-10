# Security review (US-183, NFR-SEC-12, AC-PRD-06)

Record of the security checks run before go-live. Add a section per review; keep old ones.

## 2026-11-10 — M8c

### Automated checks in CI (every push)

| Check | Tool | Gate | Status |
| --- | --- | --- | --- |
| SAST | ruff with the bandit rules (`S`) | Any finding | Clean |
| Python dependencies | pip-audit (`dependency-audit` job) | Any known vulnerability | Clean |
| JavaScript dependencies | `pnpm audit --prod --audit-level high` | High or critical | Clean |
| Images | Trivy 0.76.2, pinned by digest (`images` job) | High or critical with a fix | Clean; accepted items in `security/trivyignore` and `security/exceptions.md` |
| Authorization | authz matrix (every route × role), cross-tenant tests | Any unexpected status | 168 pass (M8b) |

Nightly: ZAP baseline (passive) against the web app and the API (`.github/workflows/nightly.yml`); a FAIL rule
fails the run. Locally on 2026-11-08: 0 FAIL; rule 10049 (non-storable content) is ignored on purpose
(`security/zap-rules.tsv`).

### Authenticated API scan (OWASP ZAP, once)

- Tool: `ghcr.io/zaproxy/zaproxy:stable`, `zap-api-scan.py` (passive and active rules) with the OpenAPI schema
  (213 URLs imported from the schema, 1,127 URLs scanned).
- Target: the development API (`TCMS_ENV=local`) in its own container with the general rate limit off, on the
  demo data. Authenticated as Ayesha (QA Manager in SPARK) with a `read_write` API token in
  `Authorization: Bearer`, so every request was signed in; CSRF does not apply to bearer tokens.
- About 70,000 requests. Answers: 23,263 × 404 and 44,181 × 422 (the scanner fills path parameters with
  placeholders, so most record routes answer "not found" or "invalid id"), 398 × 200, 218 × 202, 137 × 403,
  596 × 401 (sign-in and MFA routes probed with bad credentials), **0 × 5xx**.

Findings:

| # | Finding | Risk | Resolution |
| --- | --- | --- | --- |
| Z1 | `POST /auth/login` and `POST /auth/password/forgot` answered **500** to an email containing a NUL (0x00) character: PostgreSQL text cannot hold it and the driver raised `DataError` | Low (no data exposed; an error log line per request) | Fixed: database `DataError` now answers `422 validation_error` with "Text must not contain NUL (0x00) characters." (`api/problems.py`, `test_nul_characters_in_text_are_a_422_not_a_500`). Rescan: 0 × 5xx |
| Z2 | Private IP disclosure on `GET /me/sessions` | Low | Accepted: the list shows the signed-in user's own sessions with the address each one came from, by design (Profile › Sessions). Behind Caddy these are client addresses, not internal ones |
| Z3 | Informational only: client-error responses, authentication request identified, non-storable content, user-agent fuzzer | Info | No action |

Result after the fix: **0 FAIL, 0 high or medium findings**, 1 low (Z2, accepted).

Limits of this scan: path parameters were placeholders, so handlers that load a record by id were reached only
up to the "not found" check; those paths are covered by the authorization matrix and the API tests instead.
The single-page app was covered by the passive baseline only (no authenticated browser crawl).

### Manual review against OWASP ASVS 5.0 Level 2

Full checklist: [asvs-l2.md](asvs-l2.md). Of 253 Level 1–2 requirements, 64 do not apply (no OAuth/OIDC,
GraphQL, WebSocket, WebRTC or external identity provider in the MVP). Of the 189 that apply: 135 met, 40 partial,
14 not met; every partial and unmet item has an owner (M9, Phase 2 or accepted) in its "Gaps and follow-ups".

Fixed during the review (M8c):

| ASVS | Finding | Fix |
| --- | --- | --- |
| V12.3.2 | SMTP STARTTLS did not verify the mail server's certificate (Python's default for `starttls()` without a context), so reset links and the SMTP password could be read on the path | `smtp.starttls(context=ssl.create_default_context())` (`platform/email/__init__.py`) |
| V4.1.3, V15.3.4 | Caddy trusted `X-Forwarded-For` from private address ranges; a client on the same network could choose its own address (sign-in limit, session and audit records) | `trusted_proxies` removed from `deploy/Caddyfile`; Caddy now replaces any client value (docs/ops/deploy.md) |
| V2.4.1 | The general rate limit keyed on the raw credential, so a client sending a new made-up token per request got a fresh budget each time | Per-address cap on rejected credentials; credentials that worked in the last hour are exempt (`api/security.py`, `test_made_up_credentials_do_not_get_fresh_buckets`) |
| V3.7.2 | `returnTo` after sign-in accepted `//host` | Only same-origin paths (`routes/login.tsx`, `routes/login_.mfa.tsx`) |

Open items to decide before go-live (M9), from the checklist:

- The lockout answers 423 for the right password and 401 for a wrong one while an account is locked, so guessing
  can continue during the lockout (V6.3.1). docs/02 §3.3 chose this to avoid revealing which emails exist; the
  product owner should confirm or change it.
- Session and CSRF cookies without the `__Host-` prefix (V3.3.1).
- The app connects to MinIO with the root credentials and every app container gets the owner database URL
  (V13.2.2, V13.3.2).
- Invitation and reset tokens appear in URL paths, so access logs record them (V14.2.1, V16.2.5).
- No size or entry-count limit when unpacking XLSX imports (V5.2.3).
- Security events (authorization denials, CSRF failures, rejected API tokens) are not logged as such (V16.3).

### Other security tests

- TCMS-137 upload type and size: `tests/integration/test_storage.py`, attachment API tests (413/415).
- TCMS-138 Markdown XSS: `frontend/src/components/common/Markdown.test.tsx` renders eleven payloads (script,
  event handlers, `javascript:`/`vbscript:`/`data:` links, iframes, inline styles); no script runs and no
  dangerous attribute or URL survives. Raw HTML is never rendered (react-markdown default).
- Response headers, rate limit, production OpenAPI: `tests/api/test_security.py`.
