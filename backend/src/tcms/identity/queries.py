"""Public read functions of the identity module (for routers and other modules)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tcms.core import clock
from tcms.core.permissions import RoleCode
from tcms.identity import repository as repo
from tcms.identity import rules
from tcms.identity.auth import Authenticated
from tcms.identity.models import ApiToken, Invitation, ProjectMember, SessionRow, User, UserMfa


@dataclass(frozen=True)
class UserRef:
    id: UUID
    display_name: str
    email: str
    is_active: bool


@dataclass(frozen=True)
class Membership:
    project_id: UUID
    role_code: str
    role_name: str
    permissions: frozenset[str]


@dataclass(frozen=True)
class Me:
    user: UserRef
    time_zone: str
    organization_id: UUID
    is_org_admin: bool
    mfa_enrolled: bool
    mfa_required: bool
    memberships: list[Membership]
    org_permissions: frozenset[str]


def _restriction(auth: Authenticated) -> rules.TokenRestriction | None:
    if auth.token_id is None or auth.token_scope is None:
        return None
    return rules.TokenRestriction(auth.token_scope, auth.token_project_id)


def user_refs(s: Session, user_ids: set[UUID]) -> dict[UUID, UserRef]:
    if not user_ids:
        return {}
    rows = s.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    return {u.id: UserRef(u.id, u.display_name, u.email, u.is_active) for u in rows}


def memberships(s: Session, auth: Authenticated) -> list[Membership]:
    perms = repo.role_permission_map(s)
    roles = {r.id: r for r in repo.roles(s)}
    out = []
    for m in repo.memberships_of_user(s, auth.organization_id, auth.user_id):
        if auth.token_project_id is not None and m.project_id != auth.token_project_id:
            continue
        role = roles[m.role_id]
        effective = rules.project_permissions(
            is_org_admin=auth.is_org_admin,
            role_permissions=perms.get(m.role_id, frozenset()),
            token=_restriction(auth),
        )
        out.append(Membership(m.project_id, role.code, role.name, effective or frozenset()))
    return out


def project_permissions(s: Session, auth: Authenticated, project_id: UUID) -> frozenset[str] | None:
    """Effective permissions in `project_id`, or None if the caller may not see it (→ 404)."""
    if auth.token_project_id is not None and auth.token_project_id != project_id:
        return None
    member = repo.membership(s, auth.organization_id, project_id, auth.user_id)
    role_perms = repo.role_permission_map(s).get(member.role_id, frozenset()) if member else None
    return rules.project_permissions(
        is_org_admin=auth.is_org_admin, role_permissions=role_perms, token=_restriction(auth)
    )


def is_project_member(s: Session, auth: Authenticated, project_id: UUID) -> bool:
    return repo.membership(s, auth.organization_id, project_id, auth.user_id) is not None


def member_project_ids(s: Session, auth: Authenticated) -> set[UUID]:
    return {m.project_id for m in repo.memberships_of_user(s, auth.organization_id, auth.user_id)}


def org_permissions(s: Session, auth: Authenticated) -> frozenset[str]:
    qa = repo.system_role(s, RoleCode.qa_manager.value)
    somewhere = qa is not None and repo.is_qa_manager_somewhere(s, auth.organization_id, auth.user_id, qa.id)
    return rules.org_permissions(
        is_org_admin=auth.is_org_admin,
        is_qa_manager_somewhere=somewhere,
        policy=auth.policy,
        token=_restriction(auth),
    )


def me(s: Session, auth: Authenticated) -> Me:
    user = repo.user_by_id(s, auth.user_id)
    assert user is not None
    return Me(
        user=UserRef(user.id, user.display_name, user.email, user.is_active),
        time_zone=user.time_zone,
        organization_id=auth.organization_id,
        is_org_admin=auth.is_org_admin,
        mfa_enrolled=auth.mfa_enrolled or repo.mfa_for(s, user.id) is not None,
        mfa_required=rules.mfa_required(is_org_admin=auth.is_org_admin, policy=auth.policy),
        memberships=memberships(s, auth),
        org_permissions=org_permissions(s, auth),
    )


@dataclass(frozen=True)
class ProjectMemberRow:
    user: UserRef
    role_code: str
    role_name: str
    granted_at: datetime


def project_members(s: Session, org_id: UUID, project_id: UUID) -> list[ProjectMemberRow]:
    return [
        ProjectMemberRow(UserRef(u.id, u.display_name, u.email, u.is_active), r.code, r.name, m.granted_at)
        for m, u, r in repo.project_memberships(s, org_id, project_id)
    ]


def member_counts(s: Session, org_id: UUID, project_ids: list[UUID]) -> dict[UUID, int]:
    if not project_ids:
        return {}
    rows = s.execute(
        select(ProjectMember.project_id, func.count())
        .where(ProjectMember.organization_id == org_id, ProjectMember.project_id.in_(project_ids))
        .group_by(ProjectMember.project_id)
    ).all()
    return {pid: int(n) for pid, n in rows}


@dataclass(frozen=True)
class OrgMemberRow:
    user: UserRef
    is_org_admin: bool
    mfa_enrolled: bool
    last_login_at: datetime | None
    joined_at: datetime
    projects: int


def org_members(s: Session, org_id: UUID) -> list[OrgMemberRow]:
    enrolled = set(s.execute(select(UserMfa.user_id)).scalars().all())
    project_counts = dict(
        s.execute(
            select(ProjectMember.user_id, func.count())
            .where(ProjectMember.organization_id == org_id)
            .group_by(ProjectMember.user_id)
        ).all()
    )
    return [
        OrgMemberRow(
            user=UserRef(u.id, u.display_name, u.email, u.is_active),
            is_org_admin=m.is_org_admin,
            mfa_enrolled=u.id in enrolled,
            last_login_at=u.last_login_at,
            joined_at=m.joined_at,
            projects=int(project_counts.get(u.id, 0)),
        )
        for m, u in repo.org_members(s, org_id)
    ]


def active_org_user(s: Session, org_id: UUID, user_id: UUID) -> UserRef | None:
    member = repo.org_member_in(s, org_id, user_id)
    user = repo.user_by_id(s, user_id)
    if member is None or user is None:
        return None
    return UserRef(user.id, user.display_name, user.email, user.is_active)


@dataclass(frozen=True)
class RoleRow:
    code: str
    name: str
    permissions: frozenset[str]


def roles(s: Session) -> list[RoleRow]:
    perms = repo.role_permission_map(s)
    return [RoleRow(r.code, r.name, perms.get(r.id, frozenset())) for r in repo.roles(s)]


def sessions_of(s: Session, user_id: UUID) -> list[SessionRow]:
    return repo.active_sessions(s, user_id, clock.now())


def api_tokens_of(s: Session, user_id: UUID) -> list[ApiToken]:
    return repo.api_tokens_of(s, user_id)


@dataclass(frozen=True)
class InvitationRow:
    id: UUID
    email: str
    is_org_admin: bool
    project_id: UUID | None
    role_id: UUID | None
    invited_by: UUID | None
    created_at: datetime
    expires_at: datetime


def invitation_row(inv: Invitation) -> InvitationRow:
    return InvitationRow(
        inv.id,
        inv.email,
        inv.is_org_admin,
        inv.project_id,
        inv.role_id,
        inv.invited_by,
        inv.created_at,
        inv.expires_at,
    )


def pending_invitations(s: Session, org_id: UUID) -> list[InvitationRow]:
    return [invitation_row(i) for i in repo.pending_invitations(s, org_id, clock.now())]
