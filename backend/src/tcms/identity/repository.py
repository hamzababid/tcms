"""Identity data access (private to the module). Org-owned rows are filtered by organization_id."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from tcms.core.enums import TokenScope
from tcms.identity.models import (
    ApiToken,
    AuthRateLimit,
    Invitation,
    LoginAttempt,
    MfaRecoveryCode,
    OrganizationMember,
    PasswordResetToken,
    ProjectMember,
    Role,
    RolePermission,
    SessionRow,
    User,
    UserMfa,
)

# -- users ----------------------------------------------------------------------------------------


def user_by_email(s: Session, email: str) -> User | None:
    return s.execute(select(User).where(User.email == email)).scalar_one_or_none()


def user_by_id(s: Session, user_id: UUID, *, for_update: bool = False) -> User | None:
    stmt = select(User).where(User.id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def org_member(s: Session, user_id: UUID) -> OrganizationMember | None:
    return s.execute(
        select(OrganizationMember).where(OrganizationMember.user_id == user_id)
    ).scalar_one_or_none()


def org_member_in(
    s: Session, org_id: UUID, user_id: UUID, *, for_update: bool = False
) -> OrganizationMember | None:
    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id, OrganizationMember.user_id == user_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def org_members(s: Session, org_id: UUID) -> list[tuple[OrganizationMember, User]]:
    rows = s.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == org_id)
        .order_by(func.lower(User.display_name))
    ).all()
    return [(m, u) for m, u in rows]


def active_admin_count(s: Session, org_id: UUID) -> int:
    return int(
        s.execute(
            select(func.count())
            .select_from(OrganizationMember)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.is_org_admin.is_(True),
                User.is_active.is_(True),
            )
        ).scalar_one()
    )


# -- login attempts and rate limits ---------------------------------------------------------------


def failures_since(s: Session, email: str, since: datetime) -> int:
    last_success = (
        select(func.max(LoginAttempt.occurred_at))
        .where(LoginAttempt.email == email, LoginAttempt.succeeded.is_(True))
        .scalar_subquery()
    )
    return int(
        s.execute(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.email == email,
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.occurred_at >= since,
                LoginAttempt.occurred_at > func.coalesce(last_success, since),
            )
        ).scalar_one()
    )


def hit_rate_limit(s: Session, key: str, window_start: datetime) -> int:
    """Increment the fixed-window counter for `key`; returns the count in the current window."""
    stmt = pg_insert(AuthRateLimit).values(bucket_key=key, window_start=window_start, count=1)
    upsert = stmt.on_conflict_do_update(
        index_elements=[AuthRateLimit.bucket_key],
        set_={
            "count": case((AuthRateLimit.window_start == window_start, AuthRateLimit.count + 1), else_=1),
            "window_start": window_start,
        },
    ).returning(AuthRateLimit.count)
    return int(s.execute(upsert).scalar_one())


# -- sessions -------------------------------------------------------------------------------------


def session_by_token_hash(s: Session, token_hash: bytes, *, for_update: bool = False) -> SessionRow | None:
    stmt = select(SessionRow).where(SessionRow.token_hash == token_hash)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def session_by_id(s: Session, session_id: UUID) -> SessionRow | None:
    return s.get(SessionRow, session_id)


def active_sessions(s: Session, user_id: UUID, now: datetime) -> list[SessionRow]:
    return list(
        s.execute(
            select(SessionRow)
            .where(
                SessionRow.user_id == user_id,
                SessionRow.revoked_at.is_(None),
                SessionRow.expires_at > now,
            )
            .order_by(SessionRow.last_seen_at.desc())
        )
        .scalars()
        .all()
    )


def revoke_sessions(s: Session, user_id: UUID, now: datetime, *, except_id: UUID | None = None) -> int:
    stmt = update(SessionRow).where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
    if except_id is not None:
        stmt = stmt.where(SessionRow.id != except_id)
    return int(s.execute(stmt.values(revoked_at=now)).rowcount)  # type: ignore[attr-defined]


def delete_stale_sessions(s: Session, before: datetime) -> int:
    stmt = delete(SessionRow).where((SessionRow.expires_at < before) | (SessionRow.revoked_at < before))
    return int(s.execute(stmt).rowcount)  # type: ignore[attr-defined]


# -- MFA ------------------------------------------------------------------------------------------


def mfa_for(s: Session, user_id: UUID, *, for_update: bool = False) -> UserMfa | None:
    stmt = select(UserMfa).where(UserMfa.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def unused_recovery_code(s: Session, user_id: UUID, code_hash: str) -> MfaRecoveryCode | None:
    return s.execute(
        select(MfaRecoveryCode)
        .where(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.code_hash == code_hash,
            MfaRecoveryCode.used_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()


def clear_mfa(s: Session, user_id: UUID) -> None:
    s.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id))
    s.execute(delete(UserMfa).where(UserMfa.user_id == user_id))


def delete_recovery_codes(s: Session, user_id: UUID) -> None:
    s.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id))


# -- reset tokens and invitations -----------------------------------------------------------------


def reset_token(s: Session, token_hash: bytes) -> PasswordResetToken | None:
    return s.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash).with_for_update()
    ).scalar_one_or_none()


def invalidate_reset_tokens(s: Session, user_id: UUID, now: datetime) -> None:
    s.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )


def invitation_by_token(s: Session, token_hash: bytes, *, for_update: bool = False) -> Invitation | None:
    stmt = select(Invitation).where(Invitation.token_hash == token_hash)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def invitation(s: Session, org_id: UUID, invitation_id: UUID) -> Invitation | None:
    return s.execute(
        select(Invitation).where(Invitation.organization_id == org_id, Invitation.id == invitation_id)
    ).scalar_one_or_none()


def pending_invitations(s: Session, org_id: UUID, now: datetime) -> list[Invitation]:
    return list(
        s.execute(
            select(Invitation)
            .where(
                Invitation.organization_id == org_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .order_by(Invitation.created_at.desc())
        )
        .scalars()
        .all()
    )


def revoke_open_invitations(s: Session, org_id: UUID, email: str, now: datetime) -> None:
    s.execute(
        update(Invitation)
        .where(
            Invitation.organization_id == org_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


# -- API tokens -----------------------------------------------------------------------------------


def api_token_by_hash(s: Session, token_hash: bytes) -> ApiToken | None:
    return s.execute(select(ApiToken).where(ApiToken.token_hash == token_hash)).scalar_one_or_none()


def api_tokens_of(s: Session, user_id: UUID) -> list[ApiToken]:
    return list(
        s.execute(select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.created_at.desc()))
        .scalars()
        .all()
    )


def api_token_of(s: Session, user_id: UUID, token_id: UUID) -> ApiToken | None:
    return s.execute(
        select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.id == token_id)
    ).scalar_one_or_none()


def revoke_api_tokens(s: Session, user_id: UUID, now: datetime) -> int:
    return int(
        s.execute(
            update(ApiToken)
            .where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
            .values(revoked_at=now)
        ).rowcount  # type: ignore[attr-defined]
    )


def touch_api_token(s: Session, token_id: UUID, now: datetime) -> None:
    s.execute(update(ApiToken).where(ApiToken.id == token_id).values(last_used_at=now))


# -- roles and memberships ------------------------------------------------------------------------


def system_role(s: Session, code: str) -> Role | None:
    return s.execute(
        select(Role).where(Role.code == code, Role.organization_id.is_(None))
    ).scalar_one_or_none()


def roles(s: Session) -> list[Role]:
    return list(
        s.execute(select(Role).where(Role.organization_id.is_(None)).order_by(Role.id)).scalars().all()
    )


def role_permission_map(s: Session) -> dict[UUID, frozenset[str]]:
    out: dict[UUID, set[str]] = {}
    for role_id, perm in s.execute(select(RolePermission.role_id, RolePermission.permission)).all():
        out.setdefault(role_id, set()).add(perm)
    return {k: frozenset(v) for k, v in out.items()}


def membership(
    s: Session, org_id: UUID, project_id: UUID, user_id: UUID, *, for_update: bool = False
) -> ProjectMember | None:
    stmt = select(ProjectMember).where(
        ProjectMember.organization_id == org_id,
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def memberships_of_user(s: Session, org_id: UUID, user_id: UUID) -> list[ProjectMember]:
    return list(
        s.execute(
            select(ProjectMember).where(
                ProjectMember.organization_id == org_id, ProjectMember.user_id == user_id
            )
        )
        .scalars()
        .all()
    )


def project_memberships(s: Session, org_id: UUID, project_id: UUID) -> list[tuple[ProjectMember, User, Role]]:
    rows = s.execute(
        select(ProjectMember, User, Role)
        .join(User, User.id == ProjectMember.user_id)
        .join(Role, Role.id == ProjectMember.role_id)
        .where(ProjectMember.organization_id == org_id, ProjectMember.project_id == project_id)
        .order_by(func.lower(User.display_name))
    ).all()
    return [(m, u, r) for m, u, r in rows]


def org_project_memberships(s: Session, org_id: UUID) -> list[tuple[ProjectMember, Role]]:
    rows = s.execute(
        select(ProjectMember, Role)
        .join(Role, Role.id == ProjectMember.role_id)
        .where(ProjectMember.organization_id == org_id)
        .order_by(ProjectMember.granted_at)
    ).all()
    return [(m, r) for m, r in rows]


def count_role_members(s: Session, project_id: UUID, role_id: UUID, *, lock: bool = False) -> int:
    stmt = select(ProjectMember.user_id).where(
        ProjectMember.project_id == project_id, ProjectMember.role_id == role_id
    )
    if lock:
        stmt = stmt.with_for_update()
    return len(s.execute(stmt).all())


def is_qa_manager_somewhere(s: Session, org_id: UUID, user_id: UUID, qa_manager_role_id: UUID) -> bool:
    return (
        s.execute(
            select(ProjectMember.project_id)
            .where(
                ProjectMember.organization_id == org_id,
                ProjectMember.user_id == user_id,
                ProjectMember.role_id == qa_manager_role_id,
            )
            .limit(1)
        ).first()
        is not None
    )


def scope_value(scope: TokenScope | str) -> str:
    return scope.value if isinstance(scope, TokenScope) else scope
