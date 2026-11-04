"""Pure identity rules (no I/O). docs/02 §3, NFR-SEC-01/03/04."""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from importlib import resources
from uuid import UUID

from tcms.core.errors import FieldError
from tcms.core.permissions import ORG_ADMIN_PERMISSIONS, PROJECT_PERMISSIONS, READ_ONLY_PERMISSIONS
from tcms.core.policy import OrgPolicy

PASSWORD_MIN, PASSWORD_MAX = 12, 128
LOCKOUT_THRESHOLD = 10
LOCKOUT_WINDOW = timedelta(minutes=15)
LOCKOUT_DURATION = timedelta(minutes=15)
PENDING_MFA_TTL = timedelta(minutes=5)
MAX_MFA_FAILURES = 5
RESET_TOKEN_TTL = timedelta(minutes=60)
INVITATION_TTL = timedelta(days=7)
TOKEN_MAX_DAYS, TOKEN_DEFAULT_DAYS = 365, 90
SESSION_TOUCH_INTERVAL = timedelta(minutes=1)
RECOVERY_CODE_COUNT, RECOVERY_CODE_LENGTH = 10, 10


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    data = resources.files("tcms.identity").joinpath("data/common_passwords.txt.gz").read_bytes()
    return frozenset(gzip.decompress(data).decode("utf-8").split())


def password_problems(password: str, email: str | None) -> list[FieldError]:
    """docs/02 §3.3: 12–128 chars, not a common password, not the email; no composition rules."""
    problems: list[FieldError] = []
    if len(password) < PASSWORD_MIN:
        problems.append(FieldError("password", "too_short", f"Use at least {PASSWORD_MIN} characters"))
    if len(password) > PASSWORD_MAX:
        problems.append(FieldError("password", "too_long", f"Use at most {PASSWORD_MAX} characters"))
    lowered = password.lower()
    if email and lowered in (email.lower(), email.lower().split("@")[0]):
        problems.append(FieldError("password", "equals_email", "The password cannot be your email"))
    if lowered in _common_passwords():
        problems.append(FieldError("password", "too_common", "This password is too common"))
    return problems


# -- lockout --------------------------------------------------------------------------------------


def should_lock(failures_in_window: int) -> bool:
    """NFR-SEC-04: 10 failures within 15 minutes lock the account."""
    return failures_in_window >= LOCKOUT_THRESHOLD


def is_locked(locked_until: datetime | None, now: datetime) -> bool:
    return locked_until is not None and locked_until > now


def minutes_left(locked_until: datetime, now: datetime) -> int:
    return max(1, int((locked_until - now).total_seconds() // 60) + 1)


# -- sessions -------------------------------------------------------------------------------------


class SessionState(StrEnum):
    active = "active"
    revoked = "revoked"
    expired = "expired"  # absolute expiry or idle timeout


def session_state(
    *,
    revoked_at: datetime | None,
    expires_at: datetime,
    last_seen_at: datetime,
    policy: OrgPolicy,
    now: datetime,
) -> SessionState:
    if revoked_at is not None:
        return SessionState.revoked
    if now >= expires_at or now - last_seen_at > timedelta(minutes=policy.session_idle_minutes):
        return SessionState.expired
    return SessionState.active


def absolute_expiry(created: datetime, policy: OrgPolicy) -> datetime:
    return created + timedelta(hours=policy.session_absolute_hours)


def needs_touch(last_seen_at: datetime, now: datetime) -> bool:
    return now - last_seen_at >= SESSION_TOUCH_INTERVAL


# -- MFA ------------------------------------------------------------------------------------------


def mfa_required(*, is_org_admin: bool, policy: OrgPolicy) -> bool:
    """FR-AUTH-002: always for Org Admins; for everyone when the org policy says so."""
    return is_org_admin or policy.mfa_required_for_all


class MfaGate(StrEnum):
    ok = "ok"
    verify = "verify"  # enrolled, this session has not passed the second factor yet
    enroll = "enroll"  # required but not enrolled (AC-AUTH-04)


def mfa_gate(*, enrolled: bool, session_verified: bool, required: bool) -> MfaGate:
    if enrolled and not session_verified:
        return MfaGate.verify
    if required and not enrolled:
        return MfaGate.enroll
    return MfaGate.ok


# Routes allowed while enrolment is pending (docs/ops/00-review.md K10).
ENROLLMENT_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/auth/mfa/setup"),
        ("POST", "/api/v1/auth/mfa/enable"),
    }
)


# -- permissions ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenRestriction:
    scope: str  # "read" | "read_write"
    project_id: UUID | None


def project_permissions(
    *, is_org_admin: bool, role_permissions: frozenset[str] | None, token: TokenRestriction | None
) -> frozenset[str] | None:
    """Effective permissions in one project, or None when the project is not visible (→ 404)."""
    if is_org_admin:
        perms = PROJECT_PERMISSIONS
    elif role_permissions is not None:
        perms = role_permissions
    else:
        return None
    if token is not None and token.scope == "read":
        perms = perms & READ_ONLY_PERMISSIONS
    return frozenset(perms)


def org_permissions(
    *, is_org_admin: bool, is_qa_manager_somewhere: bool, policy: OrgPolicy, token: TokenRestriction | None
) -> frozenset[str]:
    """Organization-scope permissions (docs/02 §3.2)."""
    if is_org_admin:
        perms = ORG_ADMIN_PERMISSIONS - PROJECT_PERMISSIONS
    elif is_qa_manager_somewhere and policy.qa_managers_can_create_projects:
        perms = frozenset({"project.create"})
    else:
        perms = frozenset()
    if token is not None and token.scope == "read":
        perms = perms & READ_ONLY_PERMISSIONS
    return frozenset(perms)


def token_expiry(created: datetime, days: int) -> datetime:
    if not 1 <= days <= TOKEN_MAX_DAYS:
        raise ValueError("expiry must be 1–365 days")
    return created + timedelta(days=days)
