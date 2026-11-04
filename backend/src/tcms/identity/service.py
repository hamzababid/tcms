"""Identity use cases: the only write entry points of the module (docs/04 §3.2).

Authentication flows live in `tcms.identity.auth` and are re-exported here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from tcms.core import clock, ids
from tcms.core.config import Settings
from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.crypto import random_token, sha256
from tcms.core.errors import Conflict, NotFound, ValidationFailed
from tcms.core.events import DomainEvent
from tcms.core.permissions import RoleCode
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.identity import repository as repo
from tcms.identity import rules
from tcms.identity.auth import (
    API_TOKEN_PREFIX,
    Authenticated,
    IssuedSession,
    LoginResult,
    MfaSetup,
    PolicyFor,
    authenticate_api_token,
    authenticate_session,
    change_password,
    check_auth_rate_limit,
    check_password_policy,
    enroll_mfa_with_secret,
    forgot_password,
    issue_session,
    list_sessions,
    login,
    logout,
    mfa_disable,
    mfa_enable,
    mfa_setup,
    regenerate_recovery_codes,
    reset_password,
    revoke_own_session,
    verify_mfa,
)
from tcms.identity.errors import (
    AlreadyMember,
    LastOrgAdmin,
    LastQaManager,
    TokenInvalid,
    UserExists,
)
from tcms.identity.models import ApiToken, Invitation, OrganizationMember, ProjectMember, User
from tcms.identity.security import hash_password

__all__ = [
    "API_TOKEN_PREFIX",
    "AcceptedInvitation",
    "Authenticated",
    "CreatedInvitation",
    "CreatedToken",
    "IssuedSession",
    "LoginResult",
    "MembershipChanged",
    "MfaSetup",
    "PolicyFor",
    "accept_invitation",
    "add_member",
    "authenticate_api_token",
    "authenticate_session",
    "bootstrap_admin_invitation",
    "change_member_role",
    "change_password",
    "check_auth_rate_limit",
    "check_password_policy",
    "create_api_token",
    "create_invitation",
    "deactivate_user",
    "enroll_mfa_with_secret",
    "forgot_password",
    "invitation_for_token",
    "issue_session",
    "list_api_tokens",
    "list_sessions",
    "login",
    "logout",
    "mfa_disable",
    "mfa_enable",
    "mfa_setup",
    "pending_invitations",
    "purge_expired",
    "reactivate_user",
    "regenerate_recovery_codes",
    "remove_member",
    "reset_password",
    "reset_user_mfa",
    "revoke_api_token",
    "revoke_invitation",
    "revoke_own_session",
    "revoke_user_sessions",
    "set_org_admin",
    "update_profile",
    "verify_mfa",
]


@dataclass(frozen=True)
class MembershipChanged(DomainEvent):
    """docs/03 §5.4 (no in-process cache to bust in the MVP; kept for future handlers)."""

    organization_id: UUID
    project_id: UUID
    user_id: UUID


def _uid(ctx: AccessContext) -> UUID:
    if ctx.principal.user_id is None:
        raise RuntimeError("user principal required")
    return ctx.principal.user_id


# -- invitations (FR-AUTH-005) --------------------------------------------------------------------


@dataclass(frozen=True)
class CreatedInvitation:
    invitation: Invitation
    accept_url: str  # returned once (docs/ops/00-review.md G12)


def create_invitation(
    uow: UnitOfWork,
    settings: Settings,
    ctx: AccessContext,
    *,
    email: str,
    is_org_admin: bool = False,
    project_id: UUID | None = None,
    role_code: str | None = None,
    project_name: str | None = None,
) -> CreatedInvitation:
    """`project_id` must already be validated by the caller as a project of the caller's organization."""
    ctx.require("org.users.manage")
    s = uow.session
    email = email.strip().lower()
    existing = repo.user_by_email(s, email)
    if existing is not None:
        raise UserExists()
    role_id = None
    if project_id is not None:
        role = repo.system_role(s, role_code or RoleCode.viewer.value)
        if role is None:
            raise ValidationFailed("Unknown role", errors=[])
        role_id = role.id
    now = clock.now()
    org_id = ctx.principal.organization_id
    repo.revoke_open_invitations(s, org_id, email, now)
    token = random_token()
    inv = Invitation(
        id=ids.new_id(),
        organization_id=org_id,
        email=email,
        token_hash=sha256(token),
        is_org_admin=is_org_admin,
        project_id=project_id,
        role_id=role_id,
        invited_by=ctx.principal.user_id,
        expires_at=now + rules.INVITATION_TTL,
        created_at=now,
    )
    s.add(inv)
    s.flush()
    url = f"{settings.tcms_base_url}/invite/{token}"
    uow.audit(
        ctx,
        "user.invited",
        inv,
        changes={"email": [None, email], "is_org_admin": [None, is_org_admin], "role": [None, role_code]},
        summary=f"{ctx.principal.display_name or 'An administrator'} invited {email}",
    )
    uow.enqueue_job(
        "email.send",
        {
            "to": email,
            "template": "invitation",
            "context": {
                "inviter": ctx.principal.display_name or settings.tcms_product_name,
                "url": url,
                "project_name": project_name,
                "expires_at": inv.expires_at.isoformat(),
            },
        },
        organization_id=org_id,
    )
    return CreatedInvitation(inv, url)


def bootstrap_admin_invitation(
    uow: UnitOfWork, settings: Settings, *, organization_id: UUID, email: str
) -> CreatedInvitation:
    """US-020: the first Org Admin is invited by the `tcms bootstrap` CLI (review G16)."""
    ctx = AccessContext.for_principal(
        Principal.system(organization_id, "tcms bootstrap"),
        RequestMeta(request_id="cli"),
        permissions=frozenset({"org.users.manage"}),
    )
    return create_invitation(uow, settings, ctx, email=email, is_org_admin=True)


def pending_invitations(uow: UnitOfWork, ctx: AccessContext) -> list[Invitation]:
    ctx.require("org.users.manage")
    return repo.pending_invitations(uow.session, ctx.principal.organization_id, clock.now())


def revoke_invitation(uow: UnitOfWork, ctx: AccessContext, invitation_id: UUID) -> None:
    ctx.require("org.users.manage")
    inv = repo.invitation(uow.session, ctx.principal.organization_id, invitation_id)
    if inv is None or inv.accepted_at is not None or inv.revoked_at is not None:
        raise NotFound()
    inv.revoked_at = clock.now()
    uow.audit(ctx, "user.invitation_revoked", inv, summary=f"Invitation for {inv.email} revoked")


def invitation_for_token(uow: UnitOfWork, token: str) -> Invitation:
    inv = repo.invitation_by_token(uow.session, sha256(token))
    if (
        inv is None
        or inv.accepted_at is not None
        or inv.revoked_at is not None
        or inv.expires_at <= clock.now()
    ):
        raise TokenInvalid()
    return inv


@dataclass(frozen=True)
class AcceptedInvitation:
    session: IssuedSession
    user_id: UUID
    organization_id: UUID
    is_org_admin: bool


def accept_invitation(
    uow: UnitOfWork,
    *,
    token: str,
    display_name: str,
    password: str,
    time_zone: str,
    meta: RequestMeta,
    policy_for: PolicyFor,
) -> AcceptedInvitation:
    """Create the user and memberships, then sign them in (UJ-1, TCMS-008)."""
    s = uow.session
    inv = repo.invitation_by_token(s, sha256(token), for_update=True)
    now = clock.now()
    if inv is None or inv.accepted_at is not None or inv.revoked_at is not None or inv.expires_at <= now:
        raise TokenInvalid()
    if repo.user_by_email(s, inv.email) is not None:
        raise UserExists()
    check_password_policy(password, inv.email)
    user = User(
        id=ids.new_id(),
        email=inv.email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        time_zone=time_zone,
        password_changed_at=now,
        last_login_at=now,
        created_at=now,
        updated_at=now,
    )
    s.add(user)
    s.flush()
    user.created_by = user.id
    s.add(
        OrganizationMember(
            organization_id=inv.organization_id,
            user_id=user.id,
            is_org_admin=inv.is_org_admin,
            joined_at=now,
            granted_by=inv.invited_by,
        )
    )
    inv.accepted_at = now
    principal = Principal(user.id, inv.organization_id, inv.is_org_admin, display_name=user.display_name)
    ctx = AccessContext.for_principal(principal, meta)
    uow.audit(
        ctx, "user.activated", AuditTarget("user", user.id, user.email), summary=f"{user.display_name} joined"
    )
    if inv.is_org_admin:
        uow.audit(ctx, "org_admin.granted", AuditTarget("user", user.id, user.email))
    if inv.project_id is not None and inv.role_id is not None:
        s.add(
            ProjectMember(
                project_id=inv.project_id,
                user_id=user.id,
                organization_id=inv.organization_id,
                role_id=inv.role_id,
                granted_by=inv.invited_by,
                granted_at=now,
            )
        )
        uow.audit(
            ctx,
            "membership.granted",
            AuditTarget("membership", user.id, user.email, project_id=inv.project_id),
            changes={"role_id": [None, str(inv.role_id)]},
        )
    s.flush()
    policy = policy_for(inv.organization_id)
    issued = issue_session(
        uow,
        user,
        inv.organization_id,
        meta,
        expires_at=rules.absolute_expiry(now, policy),
        mfa_verified=False,
    )
    return AcceptedInvitation(issued, user.id, inv.organization_id, inv.is_org_admin)


# -- API tokens (FR-AUTH-010) ---------------------------------------------------------------------


@dataclass(frozen=True)
class CreatedToken:
    token: ApiToken
    secret: str  # shown once


def create_api_token(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    name: str,
    scope: str,
    expires_in_days: int,
    project_id: UUID | None,
) -> CreatedToken:
    """`project_id` must already be validated by the caller as a project the user can see."""
    if ctx.principal.token_id is not None:
        raise ValidationFailed("API tokens cannot create API tokens")
    now = clock.now()
    secret = API_TOKEN_PREFIX + random_token(40)
    token = ApiToken(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        user_id=_uid(ctx),
        name=name.strip(),
        token_prefix=secret[: len(API_TOKEN_PREFIX) + 8],
        token_hash=sha256(secret),
        scope=scope,
        project_id=project_id,
        expires_at=rules.token_expiry(now, expires_in_days),
        created_at=now,
    )
    uow.session.add(token)
    uow.session.flush()
    uow.audit(ctx, "api_token.created", token, changes={"name": [None, token.name], "scope": [None, scope]})
    return CreatedToken(token, secret)


def list_api_tokens(uow: UnitOfWork, ctx: AccessContext) -> list[ApiToken]:
    return repo.api_tokens_of(uow.session, _uid(ctx))


def revoke_api_token(uow: UnitOfWork, ctx: AccessContext, token_id: UUID) -> None:
    token = repo.api_token_of(uow.session, _uid(ctx), token_id)
    if token is None or token.revoked_at is not None:
        raise NotFound()
    token.revoked_at = clock.now()
    uow.audit(ctx, "api_token.revoked", token)


# -- profile --------------------------------------------------------------------------------------


def update_profile(
    uow: UnitOfWork, ctx: AccessContext, *, display_name: str | None, time_zone: str | None
) -> User:
    user = repo.user_by_id(uow.session, _uid(ctx), for_update=True)
    assert user is not None
    changes: dict[str, list[str | None]] = {}
    if display_name is not None and display_name.strip() != user.display_name:
        changes["display_name"] = [user.display_name, display_name.strip()]
        user.display_name = display_name.strip()
    if time_zone is not None and time_zone != user.time_zone:
        changes["time_zone"] = [user.time_zone, time_zone]
        user.time_zone = time_zone
    if changes:
        user.updated_at, user.updated_by, user.row_version = clock.now(), user.id, user.row_version + 1
        uow.audit(ctx, "user.updated", AuditTarget("user", user.id, user.email), changes=changes)
    return user


# -- user administration (docs/02 §3.5, US-164) ---------------------------------------------------


def _target_member(uow: UnitOfWork, ctx: AccessContext, user_id: UUID) -> tuple[OrganizationMember, User]:
    ctx.require("org.users.manage")
    member = repo.org_member_in(uow.session, ctx.principal.organization_id, user_id, for_update=True)
    user = repo.user_by_id(uow.session, user_id, for_update=True)
    if member is None or user is None:
        raise NotFound()
    return member, user


def deactivate_user(uow: UnitOfWork, ctx: AccessContext, user_id: UUID) -> None:
    """Sessions and tokens revoked; assignments stay (TCMS-011)."""
    member, user = _target_member(uow, ctx, user_id)
    if user_id == ctx.principal.user_id:
        raise Conflict("You cannot deactivate yourself", code="cannot_deactivate_self")
    if not user.is_active:
        return
    if member.is_org_admin and repo.active_admin_count(uow.session, member.organization_id) <= 1:
        raise LastOrgAdmin()
    now = clock.now()
    user.is_active = False
    user.updated_at, user.updated_by, user.row_version = now, ctx.principal.user_id, user.row_version + 1
    sessions = repo.revoke_sessions(uow.session, user.id, now)
    tokens = repo.revoke_api_tokens(uow.session, user.id, now)
    uow.audit(
        ctx,
        "user.deactivated",
        AuditTarget("user", user.id, user.email),
        changes={"is_active": [True, False]},
        extra={"sessions_revoked": sessions, "tokens_revoked": tokens},
    )


def reactivate_user(uow: UnitOfWork, ctx: AccessContext, user_id: UUID) -> None:
    _, user = _target_member(uow, ctx, user_id)
    if user.is_active:
        return
    user.is_active = True
    user.updated_at, user.updated_by, user.row_version = (
        clock.now(),
        ctx.principal.user_id,
        user.row_version + 1,
    )
    uow.audit(
        ctx,
        "user.reactivated",
        AuditTarget("user", user.id, user.email),
        changes={"is_active": [False, True]},
    )


def reset_user_mfa(uow: UnitOfWork, ctx: AccessContext, user_id: UUID, *, reason: str) -> None:
    _, user = _target_member(uow, ctx, user_id)
    if not reason.strip():
        raise ValidationFailed("A reason is required", code="reason_required")
    repo.clear_mfa(uow.session, user.id)
    repo.revoke_sessions(uow.session, user.id, clock.now())
    uow.audit(
        ctx, "auth.mfa_reset", AuditTarget("user", user.id, user.email), extra={"reason": reason.strip()}
    )


def revoke_user_sessions(uow: UnitOfWork, ctx: AccessContext, user_id: UUID) -> int:
    _, user = _target_member(uow, ctx, user_id)
    count = repo.revoke_sessions(uow.session, user.id, clock.now())
    uow.audit(ctx, "session.revoked", AuditTarget("user", user.id, user.email), extra={"count": count})
    return count


def set_org_admin(uow: UnitOfWork, ctx: AccessContext, user_id: UUID, *, is_org_admin: bool) -> None:
    member, user = _target_member(uow, ctx, user_id)
    if member.is_org_admin == is_org_admin:
        return
    if (
        not is_org_admin
        and user.is_active
        and repo.active_admin_count(uow.session, member.organization_id) <= 1
    ):
        raise LastOrgAdmin()
    member.is_org_admin = is_org_admin
    member.granted_by = ctx.principal.user_id
    action = "org_admin.granted" if is_org_admin else "org_admin.revoked"
    uow.audit(
        ctx,
        action,
        AuditTarget("user", user.id, user.email),
        changes={"is_org_admin": [not is_org_admin, is_org_admin]},
    )


# -- project memberships (FR-WS-003, BR-29) -------------------------------------------------------


def _role(uow: UnitOfWork, code: str | None) -> tuple[UUID, str]:
    role = repo.system_role(uow.session, code or RoleCode.viewer.value)
    if role is None:
        raise ValidationFailed(f"Unknown role '{code}'", code="validation_error")
    return role.id, role.code


def add_member(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    user_id: UUID,
    role_code: str | None,
    require_permission: bool = True,
) -> ProjectMember:
    """BR-29: Viewer unless a role is given. `require_permission=False` only for project creation."""
    if require_permission:
        ctx.require("project.members.manage")
    project_id = _project(ctx)
    s = uow.session
    org_id = ctx.principal.organization_id
    target = repo.org_member_in(s, org_id, user_id)
    user = repo.user_by_id(s, user_id)
    if target is None or user is None or not user.is_active:
        raise NotFound("User not found in this organization")
    if repo.membership(s, org_id, project_id, user_id) is not None:
        raise AlreadyMember()
    role_id, code = _role(uow, role_code)
    member = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        organization_id=org_id,
        role_id=role_id,
        granted_by=ctx.principal.user_id,
        granted_at=clock.now(),
    )
    s.add(member)
    s.flush()
    uow.audit(
        ctx,
        "membership.granted",
        AuditTarget("membership", user_id, user.email, project_id=project_id),
        changes={"role": [None, code]},
        summary=f"{ctx.principal.display_name or 'System'} added {user.display_name} as {_role_label(code)}",
    )
    uow.emit(MembershipChanged(org_id, project_id, user_id))
    return member


def change_member_role(
    uow: UnitOfWork, ctx: AccessContext, *, user_id: UUID, role_code: str
) -> ProjectMember:
    ctx.require("project.members.manage")
    project_id = _project(ctx)
    s = uow.session
    member = repo.membership(s, ctx.principal.organization_id, project_id, user_id, for_update=True)
    if member is None:
        raise NotFound()
    role_id, code = _role(uow, role_code)
    if member.role_id == role_id:
        return member
    _guard_last_qa_manager(uow, project_id, member)
    old = _role_code(uow, member.role_id)
    member.role_id = role_id
    member.granted_by = ctx.principal.user_id
    user = repo.user_by_id(s, user_id)
    uow.audit(
        ctx,
        "membership.changed",
        AuditTarget("membership", user_id, user.email if user else None, project_id=project_id),
        changes={"role": [old, code]},
        summary=(
            f"{ctx.principal.display_name} changed {user.display_name if user else 'a member'} "
            f"to {_role_label(code)}"
        ),
    )
    uow.emit(MembershipChanged(ctx.principal.organization_id, project_id, user_id))
    return member


def remove_member(uow: UnitOfWork, ctx: AccessContext, *, user_id: UUID) -> None:
    ctx.require("project.members.manage")
    project_id = _project(ctx)
    s = uow.session
    member = repo.membership(s, ctx.principal.organization_id, project_id, user_id, for_update=True)
    if member is None:
        raise NotFound()
    _guard_last_qa_manager(uow, project_id, member)
    old = _role_code(uow, member.role_id)
    s.delete(member)
    user = repo.user_by_id(s, user_id)
    uow.audit(
        ctx,
        "membership.revoked",
        AuditTarget("membership", user_id, user.email if user else None, project_id=project_id),
        changes={"role": [old, None]},
        summary=f"{ctx.principal.display_name} removed {user.display_name if user else 'a member'}",
    )
    uow.emit(MembershipChanged(ctx.principal.organization_id, project_id, user_id))


def _guard_last_qa_manager(uow: UnitOfWork, project_id: UUID, member: ProjectMember) -> None:
    qa_id, _ = _role(uow, RoleCode.qa_manager.value)
    if member.role_id == qa_id and repo.count_role_members(uow.session, project_id, qa_id, lock=True) <= 1:
        raise LastQaManager()


def _role_code(uow: UnitOfWork, role_id: UUID) -> str:
    for role in repo.roles(uow.session):
        if role.id == role_id:
            return role.code
    return str(role_id)


_ROLE_LABELS = {
    "qa_manager": "QA Manager",
    "qa_lead": "QA Lead",
    "qa_engineer": "QA Engineer",
    "developer": "Developer",
    "pm_ba": "PM/BA",
    "viewer": "Viewer",
}


def _role_label(code: str) -> str:
    return _ROLE_LABELS.get(code, code)


def _project(ctx: AccessContext) -> UUID:
    if ctx.project_id is None:
        raise RuntimeError("project context required")
    return ctx.project_id


# -- maintenance jobs -----------------------------------------------------------------------------


def purge_expired(uow: UnitOfWork, now: datetime | None = None) -> None:
    """sessions.cleanup: sessions 7 days after expiry/revocation; login attempts after 30 days (05 §9)."""
    from datetime import timedelta

    from sqlalchemy import delete

    from tcms.identity.models import AuthRateLimit, LoginAttempt

    current = now or clock.now()
    repo.delete_stale_sessions(uow.session, current - timedelta(days=7))
    uow.session.execute(delete(LoginAttempt).where(LoginAttempt.occurred_at < current - timedelta(days=30)))
    uow.session.execute(
        delete(AuthRateLimit).where(AuthRateLimit.window_start < current - timedelta(hours=1))
    )
