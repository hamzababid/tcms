"""Organization administration (docs/06 §4.2)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status

from tcms.api.deps import (
    Auth,
    ReadUow,
    Uow,
    app_state,
    org_context,
    resolve_row_version,
)
from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.core.errors import NotFound
from tcms.core.permissions import SYSTEM_ROLE_IDS
from tcms.core.uow import UnitOfWork
from tcms.identity import queries as identity_queries
from tcms.identity import schemas as ids
from tcms.identity import service as identity
from tcms.workspace import queries as workspace_queries
from tcms.workspace import schemas as ws
from tcms.workspace import service as workspace

router = APIRouter(prefix="/api/v1/organization", tags=["organization"])


def _org_read(org: Any, ctx: AccessContext) -> ws.OrganizationRead:
    settings = ws.OrgSettings(**workspace_queries.org_settings(org)) if ctx.has("org.manage") else None
    return ws.OrganizationRead(
        id=org.id, name=org.name, slug=org.slug, settings=settings, row_version=org.row_version
    )


@router.get("", response_model=ws.OrganizationRead)
def get_organization(
    response: Response, ctx: AccessContext = Depends(org_context), uow: UnitOfWork = ReadUow
) -> ws.OrganizationRead:
    org = workspace_queries.organization(uow.session, ctx.principal.organization_id)
    if org is None:
        raise NotFound()
    response.headers["ETag"] = f'"{org.row_version}"'
    return _org_read(org, ctx)


@router.patch("", response_model=ws.OrganizationRead)
def patch_organization(
    body: ws.OrganizationPatch,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = Depends(org_context),
    uow: UnitOfWork = Uow,
) -> ws.OrganizationRead:
    """US-021."""
    settings = body.settings.model_dump(exclude_none=True) if body.settings else None
    org = workspace.update_organization(
        uow,
        ctx,
        row_version=resolve_row_version(body.row_version, if_match),
        name=body.name,
        settings=settings,
    )
    response.headers["ETag"] = f'"{org.row_version}"'
    return _org_read(org, ctx)


@router.get("/members", response_model=list[ids.OrgMemberRead])
def list_members(
    ctx: AccessContext = Depends(org_context), uow: UnitOfWork = ReadUow
) -> list[ids.OrgMemberRead]:
    """US-164: with each member's project roles (M8b)."""
    ctx.require("org.users.manage")
    s, org_id = uow.session, ctx.principal.organization_id
    memberships = identity_queries.org_memberships(s, org_id)
    projects = {p.id: p for p in workspace_queries.projects(s, org_id, ids=None, status=None)}

    def roles_of(user_id: UUID) -> list[ids.ProjectRoleRead]:
        out = [
            ids.ProjectRoleRead(
                project_id=r.project_id,
                project_key=projects[r.project_id].key,
                project_name=projects[r.project_id].name,
                project_status=projects[r.project_id].status.value,
                role_code=r.role_code,
                role_name=r.role_name,
                granted_at=r.granted_at,
            )
            for r in memberships.get(user_id, [])
            if r.project_id in projects
        ]
        return sorted(out, key=lambda r: r.project_key)

    return [
        ids.OrgMemberRead(
            user=ids.UserRef(**vars(m.user)),
            is_org_admin=m.is_org_admin,
            mfa_enrolled=m.mfa_enrolled,
            last_login_at=m.last_login_at,
            joined_at=m.joined_at,
            projects=m.projects,
            project_roles=roles_of(m.user.id),
        )
        for m in identity_queries.org_members(s, org_id)
    ]


@router.post("/members/{user_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
def deactivate(user_id: UUID, ctx: AccessContext = Depends(org_context), uow: UnitOfWork = Uow) -> None:
    identity.deactivate_user(uow, ctx, user_id)


@router.post("/members/{user_id}/reactivate", status_code=status.HTTP_204_NO_CONTENT)
def reactivate(user_id: UUID, ctx: AccessContext = Depends(org_context), uow: UnitOfWork = Uow) -> None:
    identity.reactivate_user(uow, ctx, user_id)


@router.post("/members/{user_id}/reset-mfa", status_code=status.HTTP_204_NO_CONTENT)
def reset_mfa(
    user_id: UUID,
    body: ids.ResetMfaRequest,
    ctx: AccessContext = Depends(org_context),
    uow: UnitOfWork = Uow,
) -> None:
    identity.reset_user_mfa(uow, ctx, user_id, reason=body.reason)


@router.post("/members/{user_id}/revoke-sessions", response_model=ids.RevokedCount)
def revoke_sessions(
    user_id: UUID, ctx: AccessContext = Depends(org_context), uow: UnitOfWork = Uow
) -> ids.RevokedCount:
    return ids.RevokedCount(revoked=identity.revoke_user_sessions(uow, ctx, user_id))


@router.patch("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def patch_member(
    user_id: UUID,
    body: ids.OrgMemberPatch,
    ctx: AccessContext = Depends(org_context),
    uow: UnitOfWork = Uow,
) -> None:
    identity.set_org_admin(uow, ctx, user_id, is_org_admin=body.is_org_admin)


_ROLE_CODE_BY_ID = {UUID(v): k.value for k, v in SYSTEM_ROLE_IDS.items()}


def _invitation_read(inv: identity_queries.InvitationRow, uow: UnitOfWork) -> ids.InvitationRead:
    inviter = (
        identity_queries.user_refs(uow.session, {inv.invited_by}).get(inv.invited_by)
        if inv.invited_by
        else None
    )
    return ids.InvitationRead(
        id=inv.id,
        email=inv.email,
        is_org_admin=inv.is_org_admin,
        project_id=inv.project_id,
        role_code=_ROLE_CODE_BY_ID.get(inv.role_id) if inv.role_id else None,
        invited_by=ids.UserRef(**vars(inviter)) if inviter else None,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        expired=inv.expires_at <= clock.now(),
    )


@router.get("/invitations", response_model=list[ids.InvitationRead])
def list_invitations(
    ctx: AccessContext = Depends(org_context), uow: UnitOfWork = ReadUow
) -> list[ids.InvitationRead]:
    ctx.require("org.users.manage")
    return [
        _invitation_read(i, uow)
        for i in identity_queries.pending_invitations(uow.session, ctx.principal.organization_id)
    ]


@router.post("/invitations", response_model=ids.InvitationCreated, status_code=status.HTTP_201_CREATED)
def create_invitation(
    body: ids.InvitationCreate,
    request: Request,
    ctx: AccessContext = Depends(org_context),
    uow: UnitOfWork = Uow,
) -> ids.InvitationCreated:
    """US-015. `accept_url` is returned once (review G12)."""
    project = None
    if body.project_id is not None:
        project = workspace_queries.project_ref(uow.session, ctx.principal.organization_id, body.project_id)
        if project is None:
            raise NotFound("Project not found")
    created = identity.create_invitation(
        uow,
        app_state(request).settings,
        ctx,
        email=str(body.email),
        is_org_admin=body.is_org_admin,
        project_id=body.project_id,
        role_code=body.role_code,
        project_name=project.name if project else None,
    )
    read = _invitation_read(identity_queries.invitation_row(created.invitation), uow)
    return ids.InvitationCreated(**read.model_dump(), accept_url=created.accept_url)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: UUID, ctx: AccessContext = Depends(org_context), uow: UnitOfWork = Uow
) -> None:
    identity.revoke_invitation(uow, ctx, invitation_id)


@router.get("/roles", response_model=list[ids.RoleRead])
def roles(_: object = Auth, uow: UnitOfWork = ReadUow) -> list[ids.RoleRead]:
    """Read-only in the MVP (docs/02 §3.2)."""
    return [
        ids.RoleRead(code=r.code, name=r.name, permissions=sorted(r.permissions))
        for r in identity_queries.roles(uow.session)
    ]
