"""Authentication flows: sign-in, MFA, sessions, passwords (docs/02 §3.3–3.4, docs/03 §9.1).

Public entry points are re-exported by `tcms.identity.service`. Flows that must persist bookkeeping on
failure return an `Outcome` (docs/ops/00-review.md G1).
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from tcms.core import clock, ids
from tcms.core.config import Settings
from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.crypto import random_token, sha256
from tcms.core.errors import FieldError, NotFound, RateLimited, ValidationFailed
from tcms.core.outcome import Outcome
from tcms.core.policy import OrgPolicy
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.identity import repository as repo
from tcms.identity import rules, security
from tcms.identity.errors import (
    AccountLocked,
    InvalidCredentials,
    InvalidMfaCode,
    MfaAlreadyEnabled,
    MfaRequiredByPolicy,
    PasswordPolicy,
    SessionExpired,
    TokenInvalid,
)
from tcms.identity.models import LoginAttempt, MfaRecoveryCode, PasswordResetToken, SessionRow, User, UserMfa

PolicyFor = Callable[[UUID], OrgPolicy]
SESSION_TOKEN_LENGTH = 43
API_TOKEN_PREFIX = "tcms_"  # noqa: S105 — public prefix, not a secret


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf: str
    expires_at: datetime


@dataclass(frozen=True)
class LoginResult:
    session: IssuedSession
    mfa_required: bool
    mfa_enrollment_required: bool


@dataclass(frozen=True)
class Authenticated:
    """Who is calling, resolved from a session cookie or an API token."""

    user_id: UUID
    organization_id: UUID
    is_org_admin: bool
    display_name: str
    email: str
    policy: OrgPolicy
    session_id: UUID | None = None
    session_mfa_verified: bool = False
    mfa_enrolled: bool = False
    token_id: UUID | None = None
    token_scope: str | None = None
    token_project_id: UUID | None = None

    @property
    def principal(self) -> Principal:
        return Principal(
            user_id=self.user_id,
            organization_id=self.organization_id,
            is_org_admin=self.is_org_admin,
            display_name=self.display_name,
            token_id=self.token_id,
            token_scope=frozenset({self.token_scope}) if self.token_scope else None,
        )

    @property
    def mfa_gate(self) -> rules.MfaGate:
        if self.token_id is not None:
            return rules.MfaGate.ok  # tokens are created after full sign-in; MFA does not apply per request
        return rules.mfa_gate(
            enrolled=self.mfa_enrolled,
            session_verified=self.session_mfa_verified,
            required=rules.mfa_required(is_org_admin=self.is_org_admin, policy=self.policy),
        )


def _ctx(user: User, org_id: UUID, is_admin: bool, meta: RequestMeta) -> AccessContext:
    principal = Principal(user.id, org_id, is_admin, display_name=user.display_name)
    return AccessContext.for_principal(principal, meta)


def issue_session(
    uow: UnitOfWork, user: User, org_id: UUID, meta: RequestMeta, *, expires_at: datetime, mfa_verified: bool
) -> IssuedSession:
    token = random_token(SESSION_TOKEN_LENGTH)
    now = clock.now()
    uow.session.add(
        SessionRow(
            id=ids.new_id(),
            token_hash=sha256(token),
            user_id=user.id,
            organization_id=org_id,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            mfa_verified=mfa_verified,
            ip=meta.ip,
            user_agent=(meta.user_agent or "")[:500] or None,
        )
    )
    return IssuedSession(token=token, csrf=random_token(32), expires_at=expires_at)


# -- rate limiting --------------------------------------------------------------------------------


def check_auth_rate_limit(uow: UnitOfWork, ip: str | None, limit: int) -> None:
    """20 auth requests per minute per IP (docs/02 §3.3). Run in its own committed transaction."""
    now = clock.now()
    window = now.replace(second=0, microsecond=0)
    count = repo.hit_rate_limit(uow.session, f"auth:{ip or 'unknown'}", window)
    if count > limit:
        retry = int((window + timedelta(minutes=1) - now).total_seconds()) + 1
        raise RateLimited("Too many requests. Try again shortly.", retry_after=retry)


# -- sign-in --------------------------------------------------------------------------------------


def login(
    uow: UnitOfWork, *, email: str, password: str, meta: RequestMeta, policy_for: PolicyFor
) -> Outcome[LoginResult]:
    """docs/02 §3.3. Unknown email and wrong password are indistinguishable (AC-AUTH-02)."""
    s = uow.session
    now = clock.now()
    email = email.strip().lower()
    user = repo.user_by_email(s, email)
    password_ok = security.verify_password(user.password_hash if user else None, password)
    member = repo.org_member(s, user.id) if user else None

    if user is None or member is None:
        s.add(LoginAttempt(email=email, ip=meta.ip, succeeded=False, occurred_at=now))
        return Outcome.fail(InvalidCredentials())  # G5: no organization to audit in

    ctx = _ctx(user, member.organization_id, member.is_org_admin, meta)
    target = AuditTarget("user", user.id, user.email)

    if not password_ok:
        s.add(LoginAttempt(email=email, ip=meta.ip, succeeded=False, occurred_at=now))
        s.flush()
        uow.audit(ctx, "auth.login_failed", target, extra={"reason": "invalid_password"})
        failures = repo.failures_since(s, email, now - rules.LOCKOUT_WINDOW)
        locked_user = repo.user_by_id(s, user.id, for_update=True)
        assert locked_user is not None
        locked_user.failed_login_count = failures
        if rules.should_lock(failures) and not rules.is_locked(locked_user.locked_until, now):
            locked_user.locked_until = now + rules.LOCKOUT_DURATION
            uow.audit(ctx, "auth.locked", target, extra={"failures": failures})
        return Outcome.fail(InvalidCredentials())

    if rules.is_locked(user.locked_until, now):
        assert user.locked_until is not None
        s.add(LoginAttempt(email=email, ip=meta.ip, succeeded=False, occurred_at=now))
        uow.audit(ctx, "auth.login_failed", target, extra={"reason": "locked"})
        minutes = rules.minutes_left(user.locked_until, now)
        return Outcome.fail(AccountLocked(f"Too many attempts. Try again in {minutes} minutes."))

    if not user.is_active:
        s.add(LoginAttempt(email=email, ip=meta.ip, succeeded=False, occurred_at=now))
        uow.audit(ctx, "auth.login_failed", target, extra={"reason": "deactivated"})
        return Outcome.fail(InvalidCredentials())

    policy = policy_for(member.organization_id)
    enrolled = repo.mfa_for(s, user.id) is not None
    s.add(LoginAttempt(email=email, ip=meta.ip, succeeded=True, occurred_at=now))
    if enrolled:
        # Pending sign-in: a short-lived session that only allows the MFA challenge.
        issued = issue_session(
            uow,
            user,
            member.organization_id,
            meta,
            expires_at=now + rules.PENDING_MFA_TTL,
            mfa_verified=False,
        )
        return Outcome.ok(LoginResult(issued, mfa_required=True, mfa_enrollment_required=False))

    user.failed_login_count = 0
    user.last_login_at = now
    required = rules.mfa_required(is_org_admin=member.is_org_admin, policy=policy)
    issued = issue_session(
        uow,
        user,
        member.organization_id,
        meta,
        expires_at=rules.absolute_expiry(now, policy),
        mfa_verified=False,
    )
    uow.audit(ctx, "auth.login_succeeded", target, extra={"mfa": "not_enrolled"})
    return Outcome.ok(LoginResult(issued, mfa_required=False, mfa_enrollment_required=required))


def verify_mfa(
    uow: UnitOfWork,
    settings: Settings,
    *,
    session_token: str | None,
    code: str | None,
    recovery_code: str | None,
    meta: RequestMeta,
    policy_for: PolicyFor,
) -> Outcome[IssuedSession]:
    """Second factor for a pending sign-in. 5 failures invalidate it (docs/02 §3.3 step 5)."""
    s = uow.session
    now = clock.now()
    pending = repo.session_by_token_hash(s, sha256(session_token), for_update=True) if session_token else None
    if pending is None or pending.revoked_at is not None or pending.expires_at <= now or pending.mfa_verified:
        return Outcome.fail(SessionExpired("Your sign-in expired. Sign in again."))
    user = repo.user_by_id(s, pending.user_id)
    member = repo.org_member(s, pending.user_id)
    mfa = repo.mfa_for(s, pending.user_id, for_update=True)
    if user is None or member is None or mfa is None or not user.is_active:
        pending.revoked_at = now
        return Outcome.fail(SessionExpired("Your sign-in expired. Sign in again."))
    ctx = _ctx(user, member.organization_id, member.is_org_admin, meta)
    target = AuditTarget("user", user.id, user.email)

    method: str | None = None
    if code:
        secret = settings.keyring.decrypt(mfa.totp_secret_enc, aad=user.id.bytes).decode()
        step = security.matching_step(secret, code.strip(), now, mfa.last_used_step)
        if step is not None:
            mfa.last_used_step = step
            method = "totp"
    elif recovery_code:
        row = repo.unused_recovery_code(
            s, user.id, security.hash_recovery_code(settings.secret_key_bytes, recovery_code)
        )
        if row is not None:
            row.used_at = now
            method = "recovery_code"

    if method is None:
        pending.mfa_failed_attempts += 1
        uow.audit(ctx, "auth.login_failed", target, extra={"reason": "invalid_mfa_code"})
        if pending.mfa_failed_attempts >= rules.MAX_MFA_FAILURES:
            pending.revoked_at = now
            return Outcome.fail(SessionExpired("Too many invalid codes. Sign in again."))
        return Outcome.fail(InvalidMfaCode())

    # Rotate: the verified session gets a new identifier (no session fixation).
    pending.revoked_at = now
    user.failed_login_count = 0
    user.last_login_at = now
    policy = policy_for(member.organization_id)
    issued = issue_session(
        uow,
        user,
        member.organization_id,
        meta,
        expires_at=rules.absolute_expiry(now, policy),
        mfa_verified=True,
    )
    uow.audit(ctx, "auth.login_succeeded", target, extra={"mfa": method})
    return Outcome.ok(issued)


# -- per-request authentication -------------------------------------------------------------------


def authenticate_session(uow: UnitOfWork, token: str, *, policy_for: PolicyFor) -> Outcome[Authenticated]:
    """Validate a session cookie; touch last_seen at most once a minute (docs/03 §9.1)."""
    s = uow.session
    now = clock.now()
    row = repo.session_by_token_hash(s, sha256(token))
    if row is None:
        return Outcome.fail(SessionExpired())
    policy = policy_for(row.organization_id)
    state = rules.session_state(
        revoked_at=row.revoked_at,
        expires_at=row.expires_at,
        last_seen_at=row.last_seen_at,
        policy=policy,
        now=now,
    )
    if state is not rules.SessionState.active:
        if state is rules.SessionState.expired and row.revoked_at is None:
            row.revoked_at = now
        return Outcome.fail(SessionExpired())
    user = repo.user_by_id(s, row.user_id)
    member = repo.org_member_in(s, row.organization_id, row.user_id)
    if user is None or member is None or not user.is_active:
        row.revoked_at = now
        return Outcome.fail(SessionExpired())
    if rules.needs_touch(row.last_seen_at, now):
        row.last_seen_at = now
    return Outcome.ok(
        Authenticated(
            user_id=user.id,
            organization_id=row.organization_id,
            is_org_admin=member.is_org_admin,
            display_name=user.display_name,
            email=user.email,
            policy=policy,
            session_id=row.id,
            session_mfa_verified=row.mfa_verified,
            mfa_enrolled=repo.mfa_for(s, user.id) is not None,
        )
    )


def authenticate_api_token(uow: UnitOfWork, raw: str, *, policy_for: PolicyFor) -> Outcome[Authenticated]:
    s = uow.session
    now = clock.now()
    token = repo.api_token_by_hash(s, sha256(raw)) if raw.startswith(API_TOKEN_PREFIX) else None
    if token is None or token.revoked_at is not None or token.expires_at <= now:
        return Outcome.fail(InvalidCredentials("The API token is invalid, expired or revoked"))
    user = repo.user_by_id(s, token.user_id)
    member = repo.org_member_in(s, token.organization_id, token.user_id)
    if user is None or member is None or not user.is_active:
        return Outcome.fail(InvalidCredentials("The API token is invalid, expired or revoked"))
    if token.last_used_at is None or rules.needs_touch(token.last_used_at, now):
        repo.touch_api_token(s, token.id, now)
    return Outcome.ok(
        Authenticated(
            user_id=user.id,
            organization_id=token.organization_id,
            is_org_admin=member.is_org_admin,
            display_name=user.display_name,
            email=user.email,
            policy=policy_for(token.organization_id),
            token_id=token.id,
            token_scope=repo.scope_value(token.scope),
            token_project_id=token.project_id,
        )
    )


def logout(uow: UnitOfWork, ctx: AccessContext, session_id: UUID) -> None:
    row = repo.session_by_id(uow.session, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = clock.now()
        uow.audit(ctx, "auth.logout", AuditTarget("session", row.id))


def list_sessions(uow: UnitOfWork, user_id: UUID) -> list[SessionRow]:
    return repo.active_sessions(uow.session, user_id, clock.now())


def revoke_own_session(uow: UnitOfWork, ctx: AccessContext, session_id: UUID) -> None:
    row = repo.session_by_id(uow.session, session_id)
    if row is None or row.user_id != ctx.principal.user_id or row.revoked_at is not None:
        raise NotFound()
    row.revoked_at = clock.now()
    uow.audit(ctx, "session.revoked", AuditTarget("session", row.id))


def mark_session_mfa_verified(uow: UnitOfWork, session_id: UUID) -> None:
    row = repo.session_by_id(uow.session, session_id)
    if row is not None:
        row.mfa_verified = True


# -- MFA enrolment --------------------------------------------------------------------------------


@dataclass(frozen=True)
class MfaSetup:
    secret: str
    otpauth_uri: str
    setup_token: str


SETUP_TTL = timedelta(minutes=15)


def mfa_setup(uow: UnitOfWork, settings: Settings, ctx: AccessContext) -> MfaSetup:
    """Generate a secret (not yet active). The encrypted secret travels back in `setup_token`."""
    user_id = _uid(ctx)
    user = repo.user_by_id(uow.session, user_id)
    assert user is not None
    if repo.mfa_for(uow.session, user_id) is not None:
        raise MfaAlreadyEnabled()
    secret = security.new_totp_secret()
    expires = int((clock.now() + SETUP_TTL).timestamp())
    blob = settings.keyring.encrypt(f"{secret}:{expires}".encode(), aad=b"mfa-setup:" + user_id.bytes)
    return MfaSetup(
        secret=secret,
        otpauth_uri=security.otpauth_uri(secret, account=user.email, issuer=settings.tcms_product_name),
        setup_token=base64.urlsafe_b64encode(blob).decode(),
    )


def mfa_enable(
    uow: UnitOfWork,
    settings: Settings,
    ctx: AccessContext,
    *,
    setup_token: str,
    code: str,
    session_id: UUID | None,
) -> list[str]:
    """Activate MFA after verifying a code; returns the 10 recovery codes (shown once)."""
    user_id = _uid(ctx)
    s = uow.session
    if repo.mfa_for(s, user_id, for_update=True) is not None:
        raise MfaAlreadyEnabled()
    try:
        blob = settings.keyring.decrypt(
            base64.urlsafe_b64decode(setup_token), aad=b"mfa-setup:" + user_id.bytes
        )
        secret, _, expires = blob.decode().partition(":")
        if int(expires) < int(clock.now().timestamp()):
            raise ValueError("expired")
    except Exception as exc:
        raise TokenInvalid("The setup has expired. Start again.") from exc
    step = security.matching_step(secret, code.strip(), clock.now(), None)
    if step is None:
        raise InvalidMfaCode()
    s.add(
        UserMfa(
            user_id=user_id,
            totp_secret_enc=settings.keyring.encrypt(secret.encode(), aad=user_id.bytes),
            enrolled_at=clock.now(),
            last_used_step=step,
        )
    )
    codes = _store_recovery_codes(uow, settings, user_id)
    if session_id is not None:
        mark_session_mfa_verified(uow, session_id)
    uow.audit(ctx, "auth.mfa_enrolled", AuditTarget("user", user_id))
    return codes


def enroll_mfa_with_secret(uow: UnitOfWork, settings: Settings, ctx: AccessContext, secret: str) -> list[str]:
    """Local seed only (docs/ops/00-review.md K8/Q5): enrol a documented dev secret. Refused in production."""
    if settings.is_production:
        raise RuntimeError("enroll_mfa_with_secret is not available in production")
    user_id = _uid(ctx)
    uow.session.add(
        UserMfa(
            user_id=user_id,
            totp_secret_enc=settings.keyring.encrypt(secret.encode(), aad=user_id.bytes),
            enrolled_at=clock.now(),
            last_used_step=None,
        )
    )
    codes = _store_recovery_codes(uow, settings, user_id)
    uow.audit(ctx, "auth.mfa_enrolled", AuditTarget("user", user_id), extra={"source": "seed"})
    return codes


def _store_recovery_codes(uow: UnitOfWork, settings: Settings, user_id: UUID) -> list[str]:
    repo.delete_recovery_codes(uow.session, user_id)
    codes = security.new_recovery_codes()
    for c in codes:
        uow.session.add(
            MfaRecoveryCode(
                id=ids.new_id(),
                user_id=user_id,
                code_hash=security.hash_recovery_code(settings.secret_key_bytes, c),
                created_at=clock.now(),
            )
        )
    return codes


def mfa_disable(
    uow: UnitOfWork, settings: Settings, ctx: AccessContext, *, password: str, code: str, policy: OrgPolicy
) -> None:
    user_id = _uid(ctx)
    s = uow.session
    user = repo.user_by_id(s, user_id)
    mfa = repo.mfa_for(s, user_id, for_update=True)
    assert user is not None
    if mfa is None:
        raise NotFound("Two-step verification is not enabled")
    if rules.mfa_required(is_org_admin=ctx.principal.is_org_admin, policy=policy):
        raise MfaRequiredByPolicy()
    _require_password(user, password)
    secret = settings.keyring.decrypt(mfa.totp_secret_enc, aad=user_id.bytes).decode()
    if security.matching_step(secret, code.strip(), clock.now(), mfa.last_used_step) is None:
        raise InvalidMfaCode()
    repo.clear_mfa(s, user_id)
    uow.audit(ctx, "auth.mfa_disabled", AuditTarget("user", user_id))


def regenerate_recovery_codes(
    uow: UnitOfWork, settings: Settings, ctx: AccessContext, *, password: str
) -> list[str]:
    user_id = _uid(ctx)
    user = repo.user_by_id(uow.session, user_id)
    assert user is not None
    _require_password(user, password)
    if repo.mfa_for(uow.session, user_id) is None:
        raise NotFound("Two-step verification is not enabled")
    codes = _store_recovery_codes(uow, settings, user_id)
    uow.audit(ctx, "auth.recovery_codes_regenerated", AuditTarget("user", user_id))
    return codes


# -- passwords ------------------------------------------------------------------------------------


def _require_password(user: User, password: str) -> None:
    if not security.verify_password(user.password_hash, password):
        raise ValidationFailed(
            "The current password is incorrect",
            errors=[FieldError("current_password", "invalid", "The current password is incorrect")],
        )


def check_password_policy(password: str, email: str | None) -> None:
    problems = rules.password_problems(password, email)
    if problems:
        raise PasswordPolicy(problems[0].message, errors=problems)


def change_password(
    uow: UnitOfWork, ctx: AccessContext, *, current_password: str, new_password: str, session_id: UUID | None
) -> None:
    """Revokes the user's other sessions (docs/ops/00-review.md G13)."""
    s = uow.session
    user = repo.user_by_id(s, _uid(ctx), for_update=True)
    assert user is not None
    _require_password(user, current_password)
    check_password_policy(new_password, user.email)
    now = clock.now()
    user.password_hash = security.hash_password(new_password)
    user.password_changed_at = now
    repo.revoke_sessions(s, user.id, now, except_id=session_id)
    uow.audit(ctx, "auth.password_changed", AuditTarget("user", user.id))
    uow.enqueue_job(
        "email.send",
        {"to": user.email, "template": "password_changed", "context": {"display_name": user.display_name}},
        organization_id=ctx.principal.organization_id,
    )


def forgot_password(uow: UnitOfWork, settings: Settings, *, email: str, meta: RequestMeta) -> None:
    """Always succeeds from the caller's point of view (202, no enumeration)."""
    s = uow.session
    user = repo.user_by_email(s, email.strip().lower())
    member = repo.org_member(s, user.id) if user else None
    if user is None or member is None or not user.is_active:
        return
    now = clock.now()
    repo.invalidate_reset_tokens(s, user.id, now)
    token = random_token()
    s.add(
        PasswordResetToken(
            id=ids.new_id(),
            user_id=user.id,
            token_hash=sha256(token),
            expires_at=now + rules.RESET_TOKEN_TTL,
            created_at=now,
        )
    )
    ctx = _ctx(user, member.organization_id, member.is_org_admin, meta)
    uow.audit(ctx, "auth.password_reset_requested", AuditTarget("user", user.id))
    uow.enqueue_job(
        "email.send",
        {
            "to": user.email,
            "template": "password_reset",
            "context": {"display_name": user.display_name, "url": f"{settings.tcms_base_url}/reset/{token}"},
        },
        organization_id=member.organization_id,
    )


def reset_password(
    uow: UnitOfWork, *, token: str, new_password: str, revoke_api_tokens: bool, meta: RequestMeta
) -> None:
    """Single use, 60 min; revokes all sessions and other reset links (AC-AUTH-07, review K11)."""
    s = uow.session
    now = clock.now()
    row = repo.reset_token(s, sha256(token))
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise TokenInvalid()
    user = repo.user_by_id(s, row.user_id, for_update=True)
    member = repo.org_member(s, row.user_id)
    if user is None or member is None or not user.is_active:
        raise TokenInvalid()
    check_password_policy(new_password, user.email)
    user.password_hash = security.hash_password(new_password)
    user.password_changed_at = now
    user.locked_until = None
    user.failed_login_count = 0
    repo.invalidate_reset_tokens(s, user.id, now)
    sessions = repo.revoke_sessions(s, user.id, now)
    tokens = repo.revoke_api_tokens(s, user.id, now) if revoke_api_tokens else 0
    ctx = _ctx(user, member.organization_id, member.is_org_admin, meta)
    uow.audit(
        ctx,
        "auth.password_reset",
        AuditTarget("user", user.id),
        extra={"sessions_revoked": sessions, "tokens_revoked": tokens},
    )


# -- helpers --------------------------------------------------------------------------------------


def _uid(ctx: AccessContext) -> UUID:
    if ctx.principal.user_id is None:
        raise RuntimeError("user principal required")
    return ctx.principal.user_id
