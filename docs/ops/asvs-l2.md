# OWASP ASVS 5.0 Level 2 checklist

Assay against OWASP ASVS 5.0.0, every Level 1 and Level 2 requirement (253). Level 3 is out of scope.
Reviewed 2026-11-10 (M8c) by reading the code, configuration, tests and docs in this repository; no live
penetration test was run.

Scope: the API (`backend/src/tcms`), the single-page app (`frontend/src`), the background worker, and the
production stack in `deploy/docker-compose.prod.yml` behind Caddy (`deploy/Caddyfile`), with the CI gates in
`.github/workflows`. Phase 2 features (OIDC sign-in, tracker connectors, JUnit import) are not assessed.

How to read the status column:

- ✅ Met: implemented, and the evidence cell names the code, test or document that shows it.
- 🟡 Partial: some of the requirement is in place; the note says what is missing.
- ❌ Not met: no control in place.
- N/A: the feature the requirement covers does not exist in Assay; the note gives the reason.

Every 🟡 and ❌ item has an action in [Gaps and follow-ups](#gaps-and-follow-ups). File paths are relative to
the repository root; `backend/src/tcms/` is shortened to the module path where the context is clear.

## Summary

| Chapter | Requirements | ✅ Met | 🟡 Partial | ❌ Not met | N/A |
| --- | --- | --- | --- | --- | --- |
| V1 Encoding and Sanitization | 27 | 17 | 2 | 0 | 8 |
| V2 Validation and Business Logic | 11 | 11 | 0 | 0 | 0 |
| V3 Web Frontend Security | 19 | 15 | 1 | 2 | 1 |
| V4 API and Web Service | 10 | 2 | 2 | 0 | 6 |
| V5 File Handling | 9 | 5 | 2 | 2 | 0 |
| V6 Authentication | 35 | 21 | 5 | 2 | 7 |
| V7 Session Management | 18 | 9 | 5 | 1 | 3 |
| V8 Authorization | 7 | 5 | 2 | 0 | 0 |
| V9 Self-contained Tokens | 7 | 7 | 0 | 0 | 0 |
| V10 OAuth and OIDC | 29 | 0 | 0 | 0 | 29 |
| V11 Cryptography | 14 | 9 | 2 | 1 | 2 |
| V12 Secure Communication | 9 | 5 | 0 | 3 | 1 |
| V13 Configuration | 13 | 8 | 5 | 0 | 0 |
| V14 Data Protection | 9 | 3 | 4 | 2 | 0 |
| V15 Secure Coding and Architecture | 13 | 11 | 2 | 0 | 0 |
| V16 Security Logging and Error Handling | 16 | 7 | 8 | 1 | 0 |
| V17 WebRTC | 7 | 0 | 0 | 0 | 7 |
| **Total** | **253** | **135** | **40** | **14** | **64** |

Of the 189 applicable requirements, 135 are met, 40 partial and 14 not met. Findings on five requirements from the first review were fixed in M8c before this version: SMTP certificate checks (V12.3.2), client-supplied `X-Forwarded-For` (V4.1.3, V15.3.4), made-up tokens escaping the rate limit (V2.4.1) and `//host` in `returnTo` (V3.7.2).

## V1 Encoding and Sanitization

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V1.1.1 | 2 | Decode input to a canonical form once, before validating it | ✅ Met | No custom decoding: FastAPI and Pydantic decode once; `sanitize_file_name` NFC-normalizes before cleaning (`backend/src/tcms/platform/attachments.py`). |
| V1.1.2 | 2 | Encode or escape output last, for the interpreter that consumes it | ✅ Met | React escapes at render, the HTML email environment autoescapes (`platform/email/__init__.py`), SQL uses bound parameters. |
| V1.2.1 | 1 | Encode HTTP, HTML and XML output for its context | ✅ Met | API answers JSON only; React JSX escaping; HTML emails through Jinja `select_autoescape(["html"])`. |
| V1.2.2 | 1 | Encode untrusted data when building URLs | ✅ Met | `build_url` in `backend/src/tcms/core/references.py` applies `quote()` to `{ref}`; `url_problem` allows only http(s) with a host. |
| V1.2.3 | 1 | Encode output when building JavaScript or JSON | ✅ Met | JSON comes from Pydantic/FastAPI serializers and `JSON.stringify`; no string-built scripts. |
| V1.2.4 | 1 | Use parameterized queries or an ORM for database access | ✅ Met | SQLAlchemy binding throughout; raw `text()` in `reporting/` joins fixed fragments with bound params (scoped ruff S608 ignore in `backend/pyproject.toml`). |
| V1.2.5 | 1 | Protect against OS command injection | ✅ Met | No `subprocess` or `os.system` in `backend/src`; `ops/db/init-roles.sh` passes passwords as psql variables (`:'pw'`). |
| V1.2.6 | 2 | Protect against LDAP injection | N/A | No LDAP. |
| V1.2.7 | 2 | Protect against XPath injection | N/A | No XPath queries. |
| V1.2.8 | 2 | Configure LaTeX processors securely | N/A | No LaTeX. |
| V1.2.9 | 2 | Escape pattern metacharacters in regex or LIKE built from input | 🟡 Partial | Searches use `icontains(..., autoescape=True)`, except `TestPlan.key.icontains(q)` in `backend/src/tcms/planning/queries.py` (plan list `q`). |
| V1.3.1 | 1 | Sanitize HTML from WYSIWYG editors with a vetted library | ✅ Met | No HTML input; Markdown is rendered by react-markdown without raw HTML (`frontend/src/components/common/Markdown.tsx`, `Markdown.test.tsx`, TCMS-138). |
| V1.3.2 | 1 | Avoid eval() and dynamic code execution | ✅ Met | No `eval`, `exec` or `new Function` in `backend/src` or `frontend/src` (grep). |
| V1.3.3 | 2 | Sanitize data before it reaches a dangerous context | ✅ Met | Exports prefix formula starters (`FORMULA_START` in `backend/src/tcms/platform/spreadsheets.py`); file names sanitized. |
| V1.3.4 | 2 | Restrict user-supplied SVG to safe tags and attributes | ✅ Met | SVG is not in `ALLOWED_TYPES` (`platform/storage.py`); `test_svg_is_not_allowed` in `backend/tests/integration/test_storage.py`. |
| V1.3.5 | 2 | Sanitize or disable scriptable content such as Markdown | ✅ Met | react-markdown drops raw HTML and unsafe URL schemes by default; covered by `Markdown.test.tsx` (TCMS-138). |
| V1.3.6 | 2 | Protect against SSRF with protocol, host and port allowlists | ✅ Met | The backend never fetches user-supplied URLs; bug and requirement URLs are only stored and rendered as links (docs/03 §13 A10). |
| V1.3.7 | 2 | Do not build templates from untrusted input | ✅ Met | Jinja templates come from the package (`PackageLoader`); user data is passed only as context. |
| V1.3.8 | 2 | Sanitize input used in JNDI queries | N/A | No Java or JNDI. |
| V1.3.9 | 2 | Sanitize content sent to memcache | N/A | No memcache. |
| V1.3.10 | 2 | Sanitize format strings that could resolve maliciously | ✅ Met | `str.format` runs only on fixed templates (`SUBJECTS` in `platform/email/__init__.py`, seed SQL); user data is never the format string. |
| V1.3.11 | 2 | Sanitize input passed to mail systems (SMTP/IMAP injection) | ✅ Met | Recipients are stored, validated emails without whitespace (`email_problem` in `identity/rules.py`); subjects are fixed; `email.message` rejects CR/LF in headers. |
| V1.4.1 | 2 | Use memory-safe string and buffer handling | N/A | Python and TypeScript are memory-safe; C code (psycopg-c, libpq, libmagic) is a dependency, not app code. |
| V1.4.2 | 2 | Prevent integer overflows with range checks | N/A | Python and TypeScript are memory-safe; C code (psycopg-c, libpq, libmagic) is a dependency, not app code. |
| V1.4.3 | 2 | Release memory and clear dangling pointers | N/A | Python and TypeScript are memory-safe; C code (psycopg-c, libpq, libmagic) is a dependency, not app code. |
| V1.5.1 | 1 | Configure XML parsers restrictively; no external entities | 🟡 Partial | Only XLSX import parses XML (openpyxl on stdlib ElementTree, which does not resolve external entities); the `defusedxml` that docs/03 §13 A08 promises is not installed. |
| V1.5.2 | 2 | Deserialize untrusted data safely, with type allowlists | ✅ Met | Only JSON into Pydantic models; no pickle or YAML; job payloads are JSON. |

## V2 Validation and Business Logic

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V2.1.1 | 1 | Document input validation rules for each data item | ✅ Met | Field rules in docs/02 (e.g. §3.3 sign-in table, §9.2 attachments), enforced by each module's `schemas.py`. |
| V2.1.2 | 2 | Document consistency rules for combined data items | ✅ Met | docs/02 result lifecycle (BR-09 outcome table) and BR rules; implemented in `backend/src/tcms/execution/rules.py`. |
| V2.1.3 | 2 | Document business limits per user and globally | ✅ Met | docs/06 §2.10 rate limits, docs/02 §9.2 attachment limits, import caps (`MAX_ROWS`, `MAX_CASES` in `imports/cases.py`). |
| V2.2.1 | 1 | Validate input positively against business expectations | ✅ Met | Pydantic types, lengths and enums; filter and sort fields are allow-listed (`backend/src/tcms/core/pagination.py`). |
| V2.2.2 | 1 | Enforce input validation in a trusted service layer | ✅ Met | All checks run in API schemas and services; frontend zod schemas are convenience only. |
| V2.2.3 | 2 | Check that combinations of related items are reasonable | ✅ Met | `execution/rules.py` rejects step/outcome conflicts (`422 outcome_conflicts_with_steps`); `tests/unit/test_execution_rules.py`. |
| V2.3.1 | 1 | Process business flows in order, without skipped steps | ✅ Met | Pending MFA session allows only `/auth/mfa/verify`; enrolment gate `ENROLLMENT_ALLOWED` (`identity/rules.py`); draft→final attempt lifecycle. |
| V2.3.2 | 2 | Enforce documented business logic limits | ✅ Met | `MAX_PER_RECORD` = 50 attachments (`platform/attachments.py`), import caps, token expiry ≤ 365 days (`token_expiry`). |
| V2.3.3 | 2 | Use transactions so operations succeed fully or roll back | ✅ Met | `unit_of_work` in `backend/src/tcms/core/uow.py` commits or rolls back per request; `tests/integration/test_uow.py`. |
| V2.3.4 | 2 | Lock limited resources against double booking | ✅ Met | `row_version` checks (`core/concurrency.py`), `FOR UPDATE` reads, one draft per run; `tests/integration/test_attempt_concurrency.py`. |
| V2.4.1 | 2 | Anti-automation against excessive calls to functions | ✅ Met | `RateLimitMiddleware` (`api/security.py`): 600/min per caller, plus a per-address limit on rejected credentials so made-up tokens get no fresh bucket (`test_made_up_credentials_do_not_get_fresh_buckets`). Per process: the effective limit is replicas × 600. |

## V3 Web Frontend Security

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V3.2.1 | 1 | Stop browsers rendering responses in the wrong context | ✅ Met | API CSP `default-src 'none'`; attachments get `sandbox` CSP and `attachment` disposition except images/PDF (`CONTENT_CSP` in `api/v1/records.py`). |
| V3.2.2 | 1 | Render text with safe functions, not as HTML | ✅ Met | React text nodes only; no `dangerouslySetInnerHTML` or `innerHTML` in `frontend/src` (grep). |
| V3.3.1 | 1 | Cookies are Secure and use a __Secure- or __Host- prefix | ❌ Not met | `tcms_session` and `tcms_csrf` are Secure (`_set_session_cookies` in `api/v1/auth.py`) but have no prefix. |
| V3.3.2 | 2 | Set SameSite on each cookie according to purpose | ✅ Met | Both cookies `SameSite=Lax`, backed by the CSRF header and Origin check. |
| V3.3.3 | 2 | Use the __Host- prefix unless cookies are shared across hosts | ❌ Not met | No `__Host-` prefix, although both cookies are host-only with `path=/`. |
| V3.3.4 | 2 | Session cookie is HttpOnly and only set via Set-Cookie | ✅ Met | `tcms_session` is HttpOnly and never in a response body; `tcms_csrf` is readable by design (double submit). |
| V3.4.1 | 1 | Send HSTS on all responses, max-age at least one year | ✅ Met | Caddy `Strict-Transport-Security: max-age=31536000; includeSubDomains` (`deploy/Caddyfile`); API adds it in production. |
| V3.4.2 | 1 | CORS Allow-Origin is fixed or allowlisted | ✅ Met | No CORS middleware in `backend/src/tcms/main.py`; no `Access-Control-Allow-Origin` header is sent. |
| V3.4.3 | 2 | CSP with object-src 'none', base-uri 'none' and an allowlist | 🟡 Partial | SPA CSP has `object-src 'none'` and `script-src 'self'`, but `base-uri 'self'` and `style-src 'unsafe-inline'` (`deploy/Caddyfile`). |
| V3.4.4 | 2 | X-Content-Type-Options: nosniff on all responses | ✅ Met | Caddy and `SecurityHeadersMiddleware` (`api/security.py`); `test_api_responses_carry_security_headers` in `tests/api/test_security.py`. |
| V3.4.5 | 2 | Referrer policy prevents leaking data to third parties | ✅ Met | `strict-origin-when-cross-origin` from Caddy and the API; external links use `rel="noreferrer"`. |
| V3.4.6 | 2 | CSP frame-ancestors on every response | ✅ Met | `frame-ancestors 'none'` in the SPA and API policies, plus `X-Frame-Options: DENY`. |
| V3.5.1 | 1 | Validate origin of sensitive requests (anti-CSRF token or custom header) | ✅ Met | Double-submit `X-CSRF-Token` on cookie writes and Origin check on public POSTs (`api/deps.py`); `test_tcms_014_csrf_header_required_for_cookie_writes`. |
| V3.5.2 | 1 | Sensitive functions cannot be called without CORS preflight | ✅ Met | Writes need JSON or `X-CSRF-Token` (preflighted) and no origin is allowed; `test_cross_origin_login_rejected`. |
| V3.5.3 | 1 | Sensitive functionality uses POST, PUT, PATCH or DELETE | ✅ Met | GET routes run in `SET TRANSACTION READ ONLY` (`ReadUow`, `core/uow.py`); all changes use unsafe methods. |
| V3.5.4 | 2 | Host separate applications on separate hostnames | ✅ Met | One application per host name; user files from the same origin are sandboxed (`CONTENT_CSP`). |
| V3.5.5 | 2 | Discard postMessage data from untrusted origins | N/A | No `postMessage` listeners in `frontend/src`. |
| V3.7.1 | 2 | Use only supported, secure client-side technologies | ✅ Met | React 18 SPA built with Vite, no plugins; `pnpm audit` in `.github/workflows/ci.yml`. |
| V3.7.2 | 2 | Redirect to other hosts only via an allowlist | ✅ Met | `returnTo` must be a same-origin path: `/` not followed by `/` or `\` (`frontend/src/routes/login.tsx`, `login_.mfa.tsx`); no other redirect takes a user-supplied URL. |

## V4 API and Web Service

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V4.1.1 | 1 | Content-Type matches the body and declares a charset | 🟡 Partial | API JSON and text files get UTF-8 via Starlette; nginx serves `index.html` as `text/html` without charset (`frontend/nginx.conf`). |
| V4.1.2 | 2 | Only user-facing endpoints auto-redirect HTTP to HTTPS | 🟡 Partial | Caddy redirects every HTTP request to HTTPS, `/api/*` included. |
| V4.1.3 | 2 | Clients cannot override headers set by intermediaries | ✅ Met | Caddy trusts no proxies (`deploy/Caddyfile`), so it replaces any client `X-Forwarded-For` with the connection address; the api trusts that header and is reachable only through Caddy (no published port). |
| V4.2.1 | 2 | All components agree on HTTP message boundaries | ✅ Met | Standard parsers only (Caddy, uvicorn httptools/h11); no custom framing. |
| V4.3.1 | 2 | Limit GraphQL query depth, amount or cost | N/A | No GraphQL. |
| V4.3.2 | 2 | Disable GraphQL introspection in production | N/A | No GraphQL. |
| V4.4.1 | 1 | Use WSS for all WebSocket connections | N/A | No WebSocket endpoints (the bell polls, docs/ops/known-limitations.md L48). |
| V4.4.2 | 2 | Check Origin during the WebSocket handshake | N/A | No WebSocket endpoints (the bell polls, docs/ops/known-limitations.md L48). |
| V4.4.3 | 2 | Use compliant dedicated tokens for WebSocket sessions | N/A | No WebSocket endpoints (the bell polls, docs/ops/known-limitations.md L48). |
| V4.4.4 | 2 | Obtain WebSocket tokens through the authenticated HTTPS session | N/A | No WebSocket endpoints (the bell polls, docs/ops/known-limitations.md L48). |

## V5 File Handling

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V5.1.1 | 2 | Document allowed file types, extensions and sizes, incl. unpacked | 🟡 Partial | docs/02 §9.2 lists types and size limits; extensions and unpacked-size limits for XLSX imports are not documented. |
| V5.2.1 | 1 | Accept only file sizes the application can process | ✅ Met | Streaming limit in `storage.store` (`_LimitedHashingReader`), imports 20 MB (`imports/service.py`), Caddy 110 MB; `test_oversize_upload_is_rejected_and_not_kept`. |
| V5.2.2 | 1 | Check extension matches content type and validate content | 🟡 Partial | Content is sniffed with libmagic against the allow-list (`test_spoofed_type_is_rejected`); the file extension is never compared with it. |
| V5.2.3 | 2 | Check archives' uncompressed size and file count before extracting | ❌ Not met | XLSX imports go straight to `openpyxl.load_workbook` (`platform/spreadsheets.py` `read_tables`) with no size or entry-count check; ZIP attachments are never extracted. |
| V5.3.1 | 1 | Uploaded files are never executed as server code | ✅ Met | Files live in S3 under random keys and are streamed back with sandbox CSP; nothing is written to a web root. |
| V5.3.2 | 1 | Build file paths from internal data, not user filenames | ✅ Met | `object_key_for` builds `org/{org}/{yyyy}/{mm}/{uuid}` (`platform/storage.py`); `_local` blocks keys escaping the backup directory. |
| V5.4.1 | 2 | Ignore user filenames; set the download filename server-side | ✅ Met | Download name is the sanitized stored name, set by `content_disposition` (`platform/attachments.py`). |
| V5.4.2 | 2 | Encode served filenames per RFC 6266 | ✅ Met | `content_disposition` sends an ASCII fallback and `filename*=UTF-8''` percent-encoding. |
| V5.4.3 | 2 | Scan untrusted files with an antivirus | ❌ Not met | No scanning; docs/03 §11 lists a ClamAV hook for Phase 2. |

## V6 Authentication

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V6.1.1 | 1 | Document rate limiting and anti-automation for authentication | ✅ Met | docs/02 §3.3 (lockout 10 in 15 min, 20 auth requests/min/IP), NFR-SEC-04, docs/06 §2.10. |
| V6.1.2 | 2 | Document context-specific words banned in passwords | ❌ Not met | Only the email and its local part are refused (`password_problems` in `identity/rules.py`); no product or organization word list. |
| V6.1.3 | 2 | Document every authentication pathway and its strength | ✅ Met | docs/03 §9.1 (sessions, pending MFA, API tokens) and docs/02 §3.3–3.4 (reset, invitations, recovery codes). |
| V6.2.1 | 1 | Passwords at least 8 characters (15 recommended) | ✅ Met | Minimum 12 (`PASSWORD_MIN`); `test_password_policy_enforced` in `tests/api/test_auth.py`. |
| V6.2.2 | 1 | Users can change their password | ✅ Met | `POST /api/v1/auth/password/change`; Profile page. |
| V6.2.3 | 1 | Password change requires current and new password | ✅ Met | `change_password` calls `_require_password` (`backend/src/tcms/identity/auth.py`). |
| V6.2.4 | 1 | Reject the top 3000 common passwords that fit the policy | ✅ Met | SecLists NCSC top 100k filtered to ≥ 12 characters (`identity/data/README.md`, `_common_passwords`). |
| V6.2.5 | 1 | No character composition rules | ✅ Met | Only length, common-list and email checks (docs/02 §3.3). |
| V6.2.6 | 1 | Password fields use type=password | ✅ Met | `LoginPage.tsx`, `PasswordPages.tsx`, `InvitePage.tsx`, `ProfilePage.tsx` in `frontend/src/features`. |
| V6.2.7 | 1 | Allow paste, browser helpers and password managers | ✅ Met | No paste blocking; `autoComplete="current-password"`/`"new-password"` set. |
| V6.2.8 | 1 | Verify the password exactly as received | ✅ Met | `login` passes the raw password to Argon2 (`identity/auth.py`); no trimming or case change. |
| V6.2.9 | 2 | Allow passwords of at least 64 characters | ✅ Met | Maximum 128 (`PASSWORD_MAX` in `identity/rules.py`). |
| V6.2.10 | 2 | No periodic password rotation | ✅ Met | No password expiry; `password_changed_at` is informational. |
| V6.2.11 | 2 | Apply the context-specific word list | ❌ Not met | No such list exists (see V6.1.2). |
| V6.2.12 | 2 | Check passwords against breached password sets | 🟡 Partial | The NCSC list is breach-derived but a static top 100k; no full breach corpus or k-anonymity lookup. |
| V6.3.1 | 1 | Brute-force and credential-stuffing controls as documented | 🟡 Partial | Lockout and per-IP limit work (`test_tcms_003_account_locks_after_ten_failures`, `test_auth_rate_limit`), but a locked account answers 423 only for the right password, so guessing continues during lockout. |
| V6.3.2 | 1 | No default accounts such as root or admin | ✅ Met | First admin comes from a one-time `tcms bootstrap` invitation (`backend/src/tcms/cli.py`); `tcms seed` is refused in production. |
| V6.3.3 | 2 | Require MFA to access the application | 🟡 Partial | MFA is forced for Org Admins; others only when the org sets `mfa_required_for_all` (`mfa_required` in `identity/rules.py`). |
| V6.3.4 | 2 | No undocumented authentication pathways | ✅ Met | Only session sign-in (+TOTP or recovery code) and API tokens (`authenticated` in `api/deps.py`); dev TOTP enrolment refused in production. |
| V6.4.1 | 1 | Initial secrets are random, short-lived and single use | ✅ Met | Invitation tokens are `random_token()` (~256 bits), single use, 7 days (`INVITATION_TTL`); the user sets the password. |
| V6.4.2 | 1 | No password hints or secret questions | ✅ Met | None exist. |
| V6.4.3 | 2 | Password reset is secure and does not bypass MFA | ✅ Met | Reset tokens are single use for 60 min and revoke sessions; reset issues no session, so the next sign-in needs TOTP (`test_tcms_007_password_reset_single_use_and_revokes_sessions`). |
| V6.4.4 | 2 | Lost MFA factor requires identity proofing like enrolment | 🟡 Partial | Admin `reset-mfa` needs a reason and is audited (`test_admin_resets_user_mfa`); how the admin checks identity is not documented. |
| V6.5.1 | 2 | Lookup secrets and TOTPs are usable only once | ✅ Met | TOTP replay blocked by `last_used_step`, recovery codes get `used_at`; `test_tcms_005_totp_sign_in_and_replay_rejected`, `test_tcms_006_recovery_code_works_once`. |
| V6.5.2 | 2 | Low-entropy lookup secrets stored with a salted password hash | 🟡 Partial | Recovery codes (~49 bits) are stored as HMAC-SHA256 keyed with `TCMS_SECRET_KEY` (`hash_recovery_code`), not a salted password hash. |
| V6.5.3 | 2 | Generate lookup secrets and TOTP seeds with a CSPRNG | ✅ Met | `secrets.choice` for recovery codes, `pyotp.random_base32` for seeds (`backend/src/tcms/identity/security.py`). |
| V6.5.4 | 2 | Lookup secrets and OOB codes have at least 20 bits of entropy | ✅ Met | Recovery codes: 10 characters from a 31-character alphabet (~49 bits). |
| V6.5.5 | 2 | OTPs and OOB codes have a defined lifetime | ✅ Met | TOTP 30 s with ±1 step (`matching_step`); pending MFA session 5 min (`PENDING_MFA_TTL`). |
| V6.6.1 | 2 | Offer PSTN/SMS OTPs only with alternatives | N/A | No out-of-band authenticators (no SMS, push or emailed codes); the reset email is account recovery (V6.4.3). |
| V6.6.2 | 2 | Bind OOB requests to the original authentication | N/A | No out-of-band authenticators (no SMS, push or emailed codes); the reset email is account recovery (V6.4.3). |
| V6.6.3 | 2 | Rate-limit code-based OOB authentication | N/A | No out-of-band authenticators (no SMS, push or emailed codes); the reset email is account recovery (V6.4.3). |
| V6.8.1 | 2 | Prevent identity spoofing across multiple IdPs | N/A | No external IdP, OIDC or SAML in the MVP (no such code; docs/03 §9.1 lists OIDC for Phase 2). |
| V6.8.2 | 2 | Always validate signatures on authentication assertions | N/A | No external IdP, OIDC or SAML in the MVP (no such code; docs/03 §9.1 lists OIDC for Phase 2). |
| V6.8.3 | 2 | Process SAML assertions only once | N/A | No external IdP, OIDC or SAML in the MVP (no such code; docs/03 §9.1 lists OIDC for Phase 2). |
| V6.8.4 | 2 | Verify IdP authentication strength and recency claims | N/A | No external IdP, OIDC or SAML in the MVP (no such code; docs/03 §9.1 lists OIDC for Phase 2). |

## V7 Session Management

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V7.1.1 | 2 | Document idle timeout and absolute session lifetime | ✅ Met | NFR-SEC-03 in docs/01: 30 min idle, 12 h absolute, configurable per organization. |
| V7.1.2 | 2 | Document concurrent session limits and behaviour | ❌ Not met | Not documented; an account can hold any number of sessions. |
| V7.1.3 | 2 | Document federated session management systems | N/A | No SSO or federation. |
| V7.2.1 | 1 | Verify session tokens in a trusted backend | ✅ Met | `authenticate_session` looks up the SHA-256 of the cookie in `sessions` (`identity/auth.py`). |
| V7.2.2 | 1 | Use dynamic session tokens, not static API secrets | ✅ Met | A new random reference token per sign-in; API tokens are separate, per user and expiring. |
| V7.2.3 | 1 | Reference tokens are unique and CSPRNG-generated (≥128 bits) | ✅ Met | `random_token(43)` alphanumeric from `secrets` (~256 bits, `backend/src/tcms/core/crypto.py`). |
| V7.2.4 | 1 | Issue a new token on (re)authentication and end the old one | 🟡 Partial | MFA verify revokes the pending session and issues a new one; `/auth/login` does not revoke a session cookie already present. |
| V7.3.1 | 2 | Enforce an inactivity timeout | ✅ Met | Idle check in `session_state` (`identity/rules.py`); `test_tcms_009_idle_session_expires`. |
| V7.3.2 | 2 | Enforce an absolute maximum session lifetime | ✅ Met | `expires_at` from `absolute_expiry`; `test_absolute_session_expiry`. |
| V7.4.1 | 1 | Terminated sessions cannot be used again | ✅ Met | Logout sets `revoked_at`, checked on every request; `test_logout_and_session_revocation`. |
| V7.4.2 | 1 | Disabling an account ends all its sessions | ✅ Met | Deactivation revokes sessions and API tokens; `test_tcms_011_deactivated_user_sessions_and_tokens_revoked`. |
| V7.4.3 | 2 | Offer to end other sessions after an authentication factor changes | 🟡 Partial | Password change and reset revoke other sessions; MFA enable, disable and recovery-code regeneration do not. |
| V7.4.4 | 2 | Visible logout on every authenticated page | ✅ Met | Sign out in the user menu of `frontend/src/app/AppShell.tsx`. |
| V7.4.5 | 2 | Admins can end sessions of one user or all users | 🟡 Partial | Per user: `POST /organization/members/{id}/revoke-sessions`; no action for all users. |
| V7.5.1 | 2 | Full re-authentication before changing authentication attributes | 🟡 Partial | Password change, MFA disable and recovery codes need the password; MFA enrolment and API token creation do not (email is not editable). |
| V7.5.2 | 2 | View and end sessions after re-authenticating | 🟡 Partial | `GET`/`DELETE /me/sessions` exist; ending one needs no re-authentication and there is no "end all others". |
| V7.6.1 | 2 | RP and IdP session lifetimes behave as documented | N/A | No federation. |
| V7.6.2 | 2 | Create sessions only with user consent or action | N/A | No federation or silent SSO. |

## V8 Authorization

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V8.1.1 | 1 | Document function- and data-level authorization rules | ✅ Met | docs/02 §3.1–3.2 permission catalog and roles; docs/03 §9.2 resolution order. |
| V8.1.2 | 2 | Document field-level read and write access rules | 🟡 Partial | No field-level rules document; exposure is defined only by request and response schemas. |
| V8.2.1 | 1 | Restrict function-level access to explicit permissions | ✅ Met | `ctx.require(...)` in services; `tests/api/test_authz_matrix.py` covers every route × role. |
| V8.2.2 | 1 | Restrict data access to specific items (no IDOR) | ✅ Met | `project_context_from` resolves the owner and answers 404 across orgs (`api/deps.py`); `test_tcms_013_cross_tenant_and_non_member_access_is_404`. |
| V8.2.3 | 2 | Restrict field-level access (no BOPLA) | ✅ Met | Request models use `extra="forbid"`; routes declare explicit `response_model` schemas. |
| V8.3.1 | 1 | Enforce authorization in a trusted service layer | ✅ Met | Permissions are computed per request on the server (`identity_queries.project_permissions`); `frontend/src/lib/permissions.ts` only hides UI. |
| V8.4.1 | 2 | Cross-tenant controls in multi-tenant applications | 🟡 Partial | Queries are organization-scoped and tested; known exception L55: installation jobs are visible and retryable by every organization's admins. |

## V9 Self-contained Tokens

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V9.1.1 | 1 | Validate self-contained tokens by signature or MAC | ✅ Met | The only self-contained token, the MFA `setup_token`, is AES-256-GCM; the tag is checked in `KeyRing.decrypt` (`core/crypto.py`). |
| V9.1.2 | 1 | Allow only allowlisted token algorithms | ✅ Met | The algorithm is fixed (AES-GCM); the token carries no algorithm field. |
| V9.1.3 | 1 | Token keys come from trusted, preconfigured sources | ✅ Met | Keys from `TCMS_ENCRYPTION_KEYS` (secret file); unknown key ids are rejected. |
| V9.2.1 | 1 | Enforce the token validity period | ✅ Met | `mfa_enable` rejects setup tokens past their embedded 15-minute expiry (`identity/auth.py`). |
| V9.2.2 | 2 | Check token type and purpose | ✅ Met | AAD `mfa-setup:` + user id separates setup tokens from stored TOTP ciphertexts. |
| V9.2.3 | 2 | Accept only tokens meant for this service (audience) | ✅ Met | Bound to the user id through AAD; only Assay issues and reads them. |
| V9.2.4 | 2 | Restrict audience when one key issues tokens for several audiences | ✅ Met | The shared key ring uses a distinct AAD per purpose. |

## V10 OAuth and OIDC

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V10.1.1 | 2 | Send tokens only to components that need them | N/A | Assay is neither an OAuth client nor an OAuth server; API tokens are opaque bearer tokens (no OAuth/OIDC code). |
| V10.1.2 | 2 | Accept authorization server values only from flows it started | N/A | Assay is neither an OAuth client nor an OAuth server; API tokens are opaque bearer tokens (no OAuth/OIDC code). |
| V10.2.1 | 2 | OAuth client protects the code flow against CSRF | N/A | Assay is not an OAuth client (no OAuth/OIDC code; OIDC sign-in is Phase 2, docs/03 §9.1). |
| V10.2.2 | 2 | OAuth client defends against mix-up attacks | N/A | Assay is not an OAuth client (no OAuth/OIDC code; OIDC sign-in is Phase 2, docs/03 §9.1). |
| V10.3.1 | 2 | Resource server checks access token audience | N/A | Assay is not an OAuth resource server; its API tokens are its own opaque tokens. |
| V10.3.2 | 2 | Resource server enforces delegated authorization claims | N/A | Assay is not an OAuth resource server; its API tokens are its own opaque tokens. |
| V10.3.3 | 2 | Resource server identifies users by non-reassignable claims | N/A | Assay is not an OAuth resource server; its API tokens are its own opaque tokens. |
| V10.3.4 | 2 | Resource server checks authentication strength claims | N/A | Assay is not an OAuth resource server; its API tokens are its own opaque tokens. |
| V10.4.1 | 1 | Validate redirect URIs by exact match against an allowlist | N/A | Assay is not an OAuth authorization server. |
| V10.4.2 | 1 | Authorization codes usable only once | N/A | Assay is not an OAuth authorization server. |
| V10.4.3 | 1 | Authorization codes are short-lived | N/A | Assay is not an OAuth authorization server. |
| V10.4.4 | 1 | Allow clients only the grants they need | N/A | Assay is not an OAuth authorization server. |
| V10.4.5 | 1 | Mitigate refresh token replay for public clients | N/A | Assay is not an OAuth authorization server. |
| V10.4.6 | 2 | Require PKCE for the code grant | N/A | Assay is not an OAuth authorization server. |
| V10.4.7 | 2 | Restrict unauthenticated dynamic client registration | N/A | Assay is not an OAuth authorization server. |
| V10.4.8 | 2 | Refresh tokens have an absolute expiry | N/A | Assay is not an OAuth authorization server. |
| V10.4.9 | 2 | Users can revoke refresh and reference tokens | N/A | Assay is not an OAuth authorization server. |
| V10.4.10 | 2 | Authenticate confidential clients on backchannel requests | N/A | Assay is not an OAuth authorization server. |
| V10.4.11 | 2 | Assign clients only the scopes they need | N/A | Assay is not an OAuth authorization server. |
| V10.5.1 | 2 | Mitigate ID token replay (nonce) | N/A | Assay is not an OIDC relying party in the MVP. |
| V10.5.2 | 2 | Identify users by the sub claim | N/A | Assay is not an OIDC relying party in the MVP. |
| V10.5.3 | 2 | Reject authorization server impersonation via metadata | N/A | Assay is not an OIDC relying party in the MVP. |
| V10.5.4 | 2 | Check the ID token audience | N/A | Assay is not an OIDC relying party in the MVP. |
| V10.5.5 | 2 | Mitigate forced logout in back-channel logout | N/A | Assay is not an OIDC relying party in the MVP. |
| V10.6.1 | 2 | OpenID Provider allows only safe response modes | N/A | Assay is not an OpenID Provider. |
| V10.6.2 | 2 | OpenID Provider mitigates forced logout | N/A | Assay is not an OpenID Provider. |
| V10.7.1 | 2 | Authorization server gets consent for each request | N/A | No OAuth consent flows. |
| V10.7.2 | 2 | Consent prompts explain what is consented to | N/A | No OAuth consent flows. |
| V10.7.3 | 2 | Users can review and revoke consents | N/A | No OAuth consent flows. |

## V11 Cryptography

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V11.1.1 | 2 | Documented key management policy and lifecycle | 🟡 Partial | Key format and rotation by key id in `docs/ops/environment.md`, key storage in `docs/ops/deploy.md`; no rotation schedule, re-encryption or destruction procedure. |
| V11.1.2 | 2 | Maintain a cryptographic inventory | ❌ Not met | No inventory of keys, algorithms and certificates; the facts are spread over docs/03 §13 and the code. |
| V11.2.1 | 2 | Use industry-validated crypto implementations | ✅ Met | `cryptography` (AESGCM), `argon2-cffi`, `hashlib`/`hmac`, `secrets`; no custom primitives. |
| V11.2.2 | 2 | Design for crypto agility | 🟡 Partial | Key-id prefix supports key rotation and Argon2 hashes carry their parameters, but there is no rehash-on-login or re-encryption command. |
| V11.2.3 | 2 | All primitives provide at least 128-bit security | ✅ Met | AES-256, SHA-256, HMAC-SHA256, 160-bit TOTP seeds, ~256-bit tokens. |
| V11.3.1 | 1 | No insecure block modes or weak padding | ✅ Met | Only AES-GCM (`core/crypto.py`). |
| V11.3.2 | 1 | Use only approved ciphers and modes such as AES-GCM | ✅ Met | AES-256-GCM with random 96-bit nonces. |
| V11.3.3 | 2 | Protect encrypted data against modification | ✅ Met | GCM authentication tag plus AAD bound to the user id. |
| V11.4.1 | 1 | Use only approved hash functions; never MD5 | ✅ Met | SHA-256 for token hashes and HMAC; HMAC-SHA1 only inside TOTP as RFC 6238 specifies (docs/02 §3.3). |
| V11.4.2 | 2 | Store passwords with an approved, tuned password hash | ✅ Met | Argon2id with `argon2-cffi` defaults (RFC 9106 low-memory profile) in `identity/security.py`. |
| V11.4.3 | 2 | Integrity hashes are collision resistant | ✅ Met | SHA-256 for attachment integrity (`sha256` column) and token hashes. |
| V11.4.4 | 2 | Derive keys from passwords with an approved stretching KDF | N/A | No keys are derived from passwords. |
| V11.5.1 | 2 | Generate non-guessable values with a CSPRNG | ✅ Met | `secrets` for tokens, codes, nonces and request ids (`core/crypto.py`, `api/middleware.py`). |
| V11.6.1 | 2 | Use approved public-key algorithms | N/A | The application does no public-key operations; TLS is handled by Caddy (V12). |

## V12 Secure Communication

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V12.1.1 | 1 | Enable only TLS 1.2 and 1.3 | ✅ Met | Caddy defaults (TLS 1.2–1.3, `deploy/Caddyfile` sets no override); testssl.sh run on staging still pending (docs/08 §8). |
| V12.1.2 | 2 | Enable only recommended cipher suites | ✅ Met | Caddy default suites (ECDHE with AEAD ciphers only). |
| V12.1.3 | 2 | Validate mTLS client certificates before trusting them | N/A | No mTLS. |
| V12.2.1 | 1 | TLS for all external HTTP, without fallback | ✅ Met | Caddy serves HTTPS only, redirects port 80 and sends HSTS. |
| V12.2.2 | 1 | External services use publicly trusted certificates | ✅ Met | Let's Encrypt via ACME; Caddy's own CA (`local_certs`) only in the local drill (`docs/ops/deploy.md`). |
| V12.3.1 | 2 | Encrypt all connections, including databases and middleware | ❌ Not met | PostgreSQL, MinIO (`http://minio:9000`) and Caddy→api/web are plaintext on the compose network. |
| V12.3.2 | 2 | TLS clients validate server certificates | ✅ Met | SMTP STARTTLS uses `ssl.create_default_context()` (`platform/email/__init__.py`, fixed in M8c); the S3 client (boto3) verifies certificates by default. |
| V12.3.3 | 2 | Use TLS between internal HTTP services | ❌ Not met | Caddy reaches `api:8000` and `web:8080` over HTTP. |
| V12.3.4 | 2 | Internal TLS uses trusted certificates | ❌ Not met | No internal TLS exists (see V12.3.3). |

## V13 Configuration

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V13.1.1 | 2 | Document all communication needs and external services | ✅ Met | docs/03 §3–4 context and container views; `docs/ops/environment.md` lists database, S3 and SMTP settings. |
| V13.2.1 | 2 | Authenticate communication between backend components | ✅ Met | Password-authenticated DB roles, S3 keys, SMTP login; secrets read via `*_FILE` (`secret_file_values` in `core/config.py`). |
| V13.2.2 | 2 | Backend component accounts have least privilege | 🟡 Partial | The API uses the restricted `tcms_app` role (`docs/schema/01_baseline.sql`), but the app signs into MinIO with its root credentials (`deploy/docker-compose.prod.yml`). |
| V13.2.3 | 2 | No default credentials for service authentication | ✅ Met | `deploy/make-secrets.sh` generates random passwords and keys; compose reads them from secret files. |
| V13.2.4 | 2 | Allowlist the external systems the application may contact | 🟡 Partial | Targets are fixed by configuration (S3, SMTP), but no egress allowlist is enforced. |
| V13.2.5 | 2 | Server is configured with an allowlist of request destinations | 🟡 Partial | No egress restriction on the compose network (see V13.2.4). |
| V13.3.1 | 2 | Use a secrets management solution for backend secrets | 🟡 Partial | Docker secrets from `deploy/secrets/` (mode 600), kept out of env, images and git; no vault. |
| V13.3.2 | 2 | Access to secrets follows least privilege | 🟡 Partial | Every app container mounts all six app secrets, so the API holds `database_maintenance_url` (owner role) it never uses. |
| V13.4.1 | 1 | Deploy without source control metadata | ✅ Met | `.dockerignore` excludes `.git`; images copy only `backend/`, `docs/schema` and the built SPA. |
| V13.4.2 | 2 | Disable debug modes in production | ✅ Met | No debug flag; Swagger UI off and OpenAPI behind sign-in in production (`main.py`); `--reload` only in the dev image. |
| V13.4.3 | 2 | No directory listings | ✅ Met | nginx `autoindex` is off by default; Caddy has no `file_server browse`. |
| V13.4.4 | 2 | HTTP TRACE is not supported | ✅ Met | No TRACE routes: the API answers 404/405 (`test_method_not_allowed` in `tests/api/test_problems.py`). |
| V13.4.5 | 2 | Documentation and monitoring endpoints not exposed unintentionally | ✅ Met | OpenAPI needs sign-in in production (`test_openapi_needs_sign_in_in_production`); health endpoints are public by design (docs/06 §4.14). |

## V14 Data Protection

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V14.1.1 | 2 | Identify and classify sensitive data | ❌ Not met | No data classification document. |
| V14.1.2 | 2 | Document protection requirements per data class | ❌ Not met | Not documented (depends on V14.1.1). |
| V14.2.1 | 1 | Send sensitive data in body or headers, never in URLs | 🟡 Partial | Reset and invitation tokens are URL path segments (`/reset/{token}`, `GET /api/v1/auth/invitations/{token}`) and land in Caddy, gunicorn and app access logs. |
| V14.2.2 | 2 | Prevent caching of sensitive data in server components | ✅ Met | `Cache-Control: no-store` on all API responses (`SecurityHeadersMiddleware`) and on the SPA shell (`frontend/nginx.conf`). |
| V14.2.3 | 2 | Do not send sensitive data to untrusted third parties | ✅ Met | No analytics, trackers or CDN; SPA CSP `connect-src 'self'`. |
| V14.2.4 | 2 | Implement encryption, retention and logging controls per data class | 🟡 Partial | Controls exist (TOTP encryption, audit retention, log redaction) but are not tied to a classification. |
| V14.3.1 | 1 | Clear authenticated data from the client after logout | 🟡 Partial | Logout clears the React Query cache (`AppShell.tsx`); case drafts and filters stay in `localStorage`; no `Clear-Site-Data`. |
| V14.3.2 | 2 | Send anti-caching headers for sensitive data | ✅ Met | `Cache-Control: no-store` on API and SPA shell; `test_api_responses_carry_security_headers`. |
| V14.3.3 | 2 | Keep sensitive data out of browser storage | 🟡 Partial | `CaseEditor.tsx` stores unsaved case drafts (test content) in `localStorage`; the other keys are UI preferences. |

## V15 Secure Coding and Architecture

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V15.1.1 | 1 | Document remediation time frames for vulnerable components | 🟡 Partial | CI fails on known vulnerabilities and exceptions need an expiry (`security/exceptions.md`); no time frames for routine updates. |
| V15.1.2 | 2 | Maintain an SBOM of third-party components | 🟡 Partial | `backend/uv.lock` and `frontend/pnpm-lock.yaml` pin every package; no SBOM is produced. |
| V15.1.3 | 2 | Document resource-heavy functions and their defenses | ✅ Met | docs/03 §14 (jobs for large operations, statement timeouts) and `docs/ops/performance.md`. |
| V15.2.1 | 1 | Components stay within remediation time frames | ✅ Met | pip-audit, pnpm audit and Trivy gates in `.github/workflows/ci.yml`; no open exceptions in `security/exceptions.md` (2026-11-08). |
| V15.2.2 | 2 | Defend availability of resource-heavy functions | ✅ Met | Statement timeouts 15 s API / 5 min worker (`core/config.py`), background jobs for imports and exports, page and row caps. |
| V15.2.3 | 2 | Production contains only required functionality | ✅ Met | Runtime image drops dev dependencies and tests (`backend/Dockerfile`); seed and dev TOTP are refused in production. |
| V15.3.1 | 1 | Return only the required fields | ✅ Met | Explicit Pydantic `response_model` per route; job payloads are never returned (L55). |
| V15.3.2 | 2 | Do not follow redirects on outbound calls unless intended | ✅ Met | No outbound HTTP besides boto3 to the configured S3 endpoint. |
| V15.3.3 | 2 | Protect against mass assignment | ✅ Met | Request models use `extra="forbid"` in every module's `schemas.py`. |
| V15.3.4 | 2 | Proxies pass the original client IP in trusted fields | ✅ Met | See V4.1.3: Caddy sets `X-Forwarded-For` from the connection; gunicorn reads it (`--forwarded-allow-ips`). |
| V15.3.5 | 2 | Use correct types and strict comparisons | ✅ Met | mypy `strict` and Pydantic (backend), TypeScript `strict` (frontend); `compare_digest` for secrets. |
| V15.3.6 | 2 | Prevent JavaScript prototype pollution | ✅ Met | No deep merges or `__proto__` handling of untrusted objects in `frontend/src` (grep); API data typed by the generated client. |
| V15.3.7 | 2 | Defend against HTTP parameter pollution | ✅ Met | FastAPI binds each parameter from one declared source; repeated values only where a list is declared. |

## V16 Security Logging and Error Handling

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V16.1.1 | 2 | Inventory of logging per layer, events, formats and storage | 🟡 Partial | docs/03 §15 describes logging but lists `user_id`/`org_id` fields and a `/metrics` endpoint that do not exist. |
| V16.2.1 | 2 | Log entries include when, where, who and what | 🟡 Partial | Audit events carry actor and target; the `http.request` log (`api/middleware.py`) has no user or organization id. |
| V16.2.2 | 2 | Synchronized time and UTC timestamps | ✅ Met | structlog `TimeStamper(fmt="iso", utc=True)` (`core/logging.py`); audit uses `timestamptz`. |
| V16.2.3 | 2 | Log only to documented destinations | ✅ Met | stdout only (docs/03 §15); audit events in PostgreSQL. |
| V16.2.4 | 2 | Logs use a common format the processor can read | 🟡 Partial | App and Caddy log JSON; gunicorn's access log (`--access-logfile -`) is plain text and repeats the app's request log. |
| V16.2.5 | 2 | Log sensitive data according to its protection level | 🟡 Partial | Keys such as `password` and `token` are redacted (`_redact` in `core/logging.py`), but URL paths with reset and invitation tokens are logged. |
| V16.3.1 | 2 | Log all authentication attempts, successful and failed | 🟡 Partial | Sign-in, lockout, MFA and reset are audited (`identity/auth.py`); unknown emails only reach `login_attempts`, failed API tokens only the access log. |
| V16.3.2 | 2 | Log failed authorization attempts | 🟡 Partial | 403/404 denials appear only as status codes in the access log, without the caller. |
| V16.3.3 | 2 | Log documented security events and bypass attempts | 🟡 Partial | CSRF failures, 429s and validation failures are not logged as security events. |
| V16.3.4 | 2 | Log unexpected errors and security control failures | ✅ Met | `log.exception` in `api/problems.py` handlers; readiness logs database and storage failures. |
| V16.4.1 | 2 | Encode log data to prevent log injection | ✅ Met | structlog `JSONRenderer`; incoming request ids validated by `_VALID_ID` (`api/middleware.py`). |
| V16.4.2 | 2 | Protect logs from unauthorized access and modification | 🟡 Partial | Audit is append-only (trigger and REVOKE, `test_br_26_audit_append_only_sql`); container logs depend on the host's Docker setup. |
| V16.4.3 | 2 | Send logs to a logically separate system | ❌ Not met | No log shipping is configured; logs stay on the host. |
| V16.5.1 | 2 | Return generic messages for unexpected errors | ✅ Met | Unhandled errors return an `internal_error` problem without details (`test_unhandled_error_is_internal_problem`). |
| V16.5.2 | 2 | Stay secure when external resources fail | ✅ Met | S3 timeouts and retries (`make_client`), SMTP 15 s timeout inside a retried job, readiness reports failures. |
| V16.5.3 | 2 | Fail securely; no fail-open paths | ✅ Met | Exceptions roll back the unit of work (`core/uow.py`); authentication failures deny. |

## V17 WebRTC

| Req | L | Requirement | Status | Evidence / note |
| --- | --- | --- | --- | --- |
| V17.1.1 | 2 | TURN relays only to non-reserved IP addresses | N/A | No WebRTC, TURN, media or signaling servers. |
| V17.2.1 | 2 | Manage the DTLS certificate key per policy | N/A | No WebRTC, TURN, media or signaling servers. |
| V17.2.2 | 2 | Media server uses approved DTLS suites and SRTP profile | N/A | No WebRTC, TURN, media or signaling servers. |
| V17.2.3 | 2 | Media server checks SRTP authentication | N/A | No WebRTC, TURN, media or signaling servers. |
| V17.2.4 | 2 | Media server survives malformed SRTP packets | N/A | No WebRTC, TURN, media or signaling servers. |
| V17.3.1 | 2 | Signaling server survives floods | N/A | No WebRTC, TURN, media or signaling servers. |
| V17.3.2 | 2 | Signaling server survives malformed messages | N/A | No WebRTC, TURN, media or signaling servers. |

## Gaps and follow-ups

Owner: **M9** (before go-live), **Phase 2**, or **accept** (risk accepted, with the reason).

- 🟡 **V1.2.9**: Add `autoescape=True` to `TestPlan.key.icontains(q)` in `planning/queries.py`. Owner: M9.
- 🟡 **V1.5.1**: Add `defusedxml` to the runtime dependencies (openpyxl uses it automatically) or correct docs/03 §13 A08. Owner: M9.
- ❌ **V3.3.1, V3.3.3**: Rename the cookies to `__Host-tcms_session` and `__Host-tcms_csrf` (both are already Secure, host-only, `path=/`); check local http development. Owner: M9.
- 🟡 **V3.4.3**: Change `base-uri 'self'` to `base-uri 'none'`; keep `style-src 'unsafe-inline'` (Radix, Recharts) as an accepted exception. Owner: M9 (base-uri), accept (styles).
- 🟡 **V4.1.1**: Add `charset utf-8;` to `frontend/nginx.conf`. Owner: M9.
- 🟡 **V4.1.2**: API clients are configured with an https base URL; the redirect only affects misconfigured clients. Owner: accept.
- 🟡 **V5.1.1**: Document allowed extensions and the import limits (20 MB, 50,000 rows, unpacked size) in docs/02 §9.2 and docs/06 §4.13. Owner: M9.
- 🟡 **V5.2.2**: Compare the file extension with the sniffed type and reject mismatches (or rename on download). Owner: Phase 2.
- ❌ **V5.2.3**: Before `load_workbook`, open the XLSX with `zipfile` and reject files whose total uncompressed size or entry count exceeds a limit. Owner: M9.
- ❌ **V5.4.3**: ClamAV hook before an attachment becomes downloadable (docs/03 §11). Owner: Phase 2.
- ❌ **V6.1.2, V6.2.11**: Document and refuse context words ("assay", product name, organization name and slug, user's display name) in `password_problems`. Owner: M9.
- 🟡 **V6.2.12**: Self-hosted installs may be offline; keep the NCSC list and document the choice. Optional k-anonymity breach lookup later. Owner: accept.
- 🟡 **V6.3.1**: During lockout answer the same way whatever the password (or skip verification while locked) so the lock does not reveal a correct guess; update docs/02 §3.3 and TCMS-003. Owner: M9.
- 🟡 **V6.3.3**: Recommend `mfa_required_for_all` in the deployment runbook, or make it the default for new organizations. Owner: M9 (decision).
- 🟡 **V6.4.4**: Write the admin runbook for MFA resets (how to confirm identity before `reset-mfa`). Owner: M9.
- 🟡 **V6.5.2**: Codes are peppered with `TCMS_SECRET_KEY`, so a database dump alone does not allow offline guessing; switch to Argon2 only if the key and database share a backup. Owner: accept.
- ❌ **V7.1.2**: Document that parallel sessions are unlimited and that users and admins can end them. Owner: M9.
- 🟡 **V7.2.4**: On successful `/auth/login` and `/auth/mfa/verify`, revoke the session named by any incoming `tcms_session` cookie. Owner: M9.
- 🟡 **V7.4.3**: After MFA enable, disable or recovery-code regeneration, revoke other sessions or offer it in the UI. Owner: M9.
- 🟡 **V7.4.5**: Add an installation-level "end all sessions" command (`tcms revoke-sessions --all`). Owner: Phase 2.
- 🟡 **V7.5.1**: Require the current password for `/auth/mfa/setup` (or `enable`) and for API token creation. Owner: M9.
- 🟡 **V7.5.2**: Add "Sign out other sessions" with password confirmation on the Profile page. Owner: M9.
- 🟡 **V8.1.2**: Document field-level rules (who may read and write which fields) next to the permission catalog. Owner: Phase 2.
- 🟡 **V8.4.1**: Restrict installation jobs to an installation operator role (known-limitations L55). Owner: Phase 2.
- 🟡 ❌ **V11.1.1, V11.1.2**: Add a short key management and crypto inventory section to `docs/ops/deploy.md`: each key, algorithm, where it lives, rotation and destruction steps. Owner: M9.
- 🟡 **V11.2.2**: Add `check_needs_rehash` on sign-in and a `tcms reencrypt` command for key rotation. Owner: Phase 2.
- ❌ **V12.3.1, V12.3.3, V12.3.4**: Single-host compose: internal traffic stays on the host's Docker network. Require `sslmode=verify-full` and https S3 when the database or storage moves off the host. Owner: accept (single host), Phase 2 (split hosts).
- 🟡 **V13.2.2, V13.3.2**: Create a dedicated MinIO user limited to the attachments bucket for the app; mount `database_maintenance_url` only in `worker` and `migrate`, and `smtp_password` only in `worker`. Owner: M9.
- 🟡 **V13.2.4, V13.2.5**: Document the outbound destinations and recommend a host egress firewall (S3, SMTP, ACME only). Owner: accept (operator), Phase 2 (integrations).
- 🟡 **V13.3.1**: Docker secrets are adequate for a single host; support a vault-backed `*_FILE` source when needed. Owner: accept.
- 🟡 ❌ **V14.1.1, V14.1.2, V14.2.4**: Write a data classification (credentials, TOTP seeds, personal data, test content, audit) with required controls per class. Owner: M9.
- 🟡 **V14.2.1, V16.2.5**: Move the invitation token to a POST body (or URL fragment) and redact `/reset/` and `/invitations/` tokens from access logs (Caddy, gunicorn, `http.request`). Owner: M9.
- 🟡 **V14.3.1, V14.3.3**: Clear case drafts and per-user keys from `localStorage` on sign-out and send `Clear-Site-Data: "cache", "storage"` from `/auth/logout`. Owner: M9.
- 🟡 **V15.1.1**: State remediation time frames (for example critical 7 days, high 30 days, routine updates monthly) in `security/exceptions.md`. Owner: M9.
- 🟡 **V15.1.2**: Produce a CycloneDX SBOM per image in the `images` CI job (Trivy `--format cyclonedx`) and keep it with the release. Owner: M9.
- 🟡 **V16.1.1**: Correct docs/03 §15 to the actual log fields and drop or implement `/metrics`. Owner: M9.
- 🟡 **V16.2.1, V16.3.2, V16.3.3**: Add `user_id` and `org_id` to the `http.request` log and log `security.*` events for 403, CSRF failures, 429 and invalid API tokens. Owner: M9.
- 🟡 **V16.2.4**: Drop gunicorn's `--access-logfile -` (the app already logs each request as JSON). Owner: M9.
- 🟡 **V16.3.1**: Log failed API token authentication and unknown-email sign-ins as structured security events. Owner: M9.
- 🟡 ❌ **V16.4.2, V16.4.3**: Document log retention and shipping for operators (Docker log driver to a central collector). Owner: accept (operator), Phase 2 (built-in option).
