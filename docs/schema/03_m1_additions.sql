-- 03_m1_additions.sql — M1 schema additions (docs/ops/00-review.md G3, G4; docs/05 §3.1).
-- Applied by Alembic migration 0002 after 01_baseline.sql and 02_seed_system.sql. Run as tcms_owner.

BEGIN;

-- Pending sign-in (session row with mfa_verified = false) counts failed MFA codes:
-- 5 failures invalidate the pending login (docs/02 §3.3 step 5).
ALTER TABLE sessions ADD COLUMN mfa_failed_attempts smallint NOT NULL DEFAULT 0
  CHECK (mfa_failed_attempts >= 0);

-- Fixed-window counters for the auth rate limit (20 requests/min per IP, docs/02 §3.3, docs/03 §13).
CREATE TABLE auth_rate_limits (
  bucket_key    text PRIMARY KEY CHECK (char_length(bucket_key) BETWEEN 1 AND 200),
  window_start  timestamptz NOT NULL,
  count         integer NOT NULL DEFAULT 0 CHECK (count >= 0)
);
CREATE INDEX ix_auth_rate_limits__window_start ON auth_rate_limits (window_start);

GRANT SELECT, INSERT, UPDATE, DELETE ON auth_rate_limits TO tcms_app;
GRANT SELECT ON auth_rate_limits TO tcms_readonly;

COMMIT;
