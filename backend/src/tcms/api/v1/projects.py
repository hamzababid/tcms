"""Projects, members, environments, releases and activity (docs/06 §4.3)."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status

from tcms.api.deps import (
    Auth,
    get_read_uow,
    get_uow,
    org_context,
    project_context,
    project_context_allow_archived,
    project_context_from,
    resolve_row_version,
)
from tcms.core.context import AccessContext
from tcms.core.enums import ProjectStatus
from tcms.core.errors import NotFound
from tcms.core.pagination import Page, PageParams
from tcms.core.uow import UnitOfWork
from tcms.identity import queries as identity_queries
from tcms.identity import schemas as ids
from tcms.identity import service as identity
from tcms.identity.service import Authenticated
from tcms.platform.audit import queries as audit_queries
from tcms.workspace import queries as workspace_queries
from tcms.workspace import schemas as ws
from tcms.workspace import service as workspace

router = APIRouter(prefix="/api/v1", tags=["projects"])


def _etag(response: Response, row_version: int) -> None:
    response.headers["ETag"] = f'"{row_version}"'


def _project_read(p: Any, counts: ws.ProjectCounts | None = None) -> ws.ProjectRead:
    return ws.ProjectRead(
        id=p.id,
        key=p.key,
        name=p.name,
        description=p.description,
        status=p.status,
        settings=ws.ProjectSettings(**workspace_queries.project_settings(p)),
        counts=counts,
        archived_at=p.archived_at,
        created_at=p.created_at,
        updated_at=p.updated_at,
        row_version=p.row_version,
    )


# -- projects -------------------------------------------------------------------------------------


@router.get("/projects", response_model=list[ws.ProjectRead])
def list_projects(
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
    auth: Authenticated = Auth,
    uow: UnitOfWork = Depends(get_read_uow),
) -> list[ws.ProjectRead]:
    """Projects the caller can see: memberships, or all for Org Admins (docs/02 §3.2)."""
    visible = None if auth.is_org_admin else identity_queries.member_project_ids(uow.session, auth)
    if auth.token_project_id is not None:
        visible = {auth.token_project_id} & (visible if visible is not None else {auth.token_project_id})
    return [
        _project_read(p)
        for p in workspace_queries.projects(
            uow.session, auth.organization_id, ids=visible, status=status_filter
        )
    ]


@router.post("/projects", response_model=ws.ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ws.ProjectCreate,
    auth: Authenticated = Auth,
    ctx: AccessContext = Depends(org_context),
    uow: UnitOfWork = Depends(get_uow),
) -> ws.ProjectRead:
    """US-022, AC-WS-01."""
    p = workspace.create_project(
        uow, ctx, key=body.key, name=body.name, description=body.description, policy=auth.policy
    )
    return _project_read(p)


@router.get("/projects/{project_id}", response_model=ws.ProjectRead)
def get_project(
    response: Response, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_read_uow)
) -> ws.ProjectRead:
    p = workspace.get_project(uow, ctx)
    s = uow.session
    org = ctx.principal.organization_id
    counts = ws.ProjectCounts(
        members=identity_queries.member_counts(s, org, [p.id]).get(p.id, 0),
        environments=len(workspace_queries.environments(s, org, p.id, include_archived=False)),
        releases=len(workspace_queries.releases(s, org, p.id)),
    )
    _etag(response, p.row_version)
    return _project_read(p, counts)


@router.patch("/projects/{project_id}", response_model=ws.ProjectRead)
def patch_project(
    body: ws.ProjectPatch,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    auth: Authenticated = Auth,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_uow),
) -> ws.ProjectRead:
    """US-023 / FR-WS-004."""
    p = workspace.update_project(
        uow,
        ctx,
        row_version=resolve_row_version(body.row_version, if_match),
        name=body.name,
        description=body.description,
        description_set="description" in body.model_fields_set,
        settings=body.settings.model_dump(exclude_none=True) if body.settings else None,
        policy=auth.policy,
    )
    _etag(response, p.row_version)
    return _project_read(p)


@router.post("/projects/{project_id}/archive", response_model=ws.ProjectRead)
def archive_project(
    body: ws.ArchiveRequest, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_uow)
) -> ws.ProjectRead:
    """US-029 / AC-WS-02."""
    return _project_read(workspace.archive_project(uow, ctx, confirm_key=body.confirm_key))


@router.post("/projects/{project_id}/restore", response_model=ws.ProjectRead)
def restore_project(
    ctx: AccessContext = Depends(project_context_allow_archived), uow: UnitOfWork = Depends(get_uow)
) -> ws.ProjectRead:
    return _project_read(workspace.restore_project(uow, ctx))


@router.get("/projects/{project_id}/activity", response_model=Page[ws.ActivityItem])
def activity(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    entity_type: str | None = Query(default=None, max_length=50),
    actor_id: UUID | None = None,
    action: str | None = Query(default=None, max_length=100),
    occurred_at__gte: date | None = None,
    occurred_at__lte: date | None = None,
    q: str | None = Query(default=None, max_length=200),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> Page[ws.ActivityItem]:
    """US-028 / FR-WS-007: rendered audit summaries; filters as audit events (docs/06 §4.12) plus `q`."""
    ctx.require("project.view")
    params = PageParams(page=page, page_size=page_size)
    rows, total = audit_queries.project_activity(
        uow.session,
        ctx.principal.organization_id,
        ctx.pid,
        params,
        filters=audit_queries.AuditFilter(
            entity_type=entity_type,
            actor_id=actor_id,
            action=action,
            occurred_from=occurred_at__gte,
            occurred_to=occurred_at__lte,
            q=q,
        ),
    )
    return Page[ws.ActivityItem](
        items=[ws.ActivityItem.model_validate(vars(r)) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


# -- members --------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/members", response_model=list[ids.ProjectMemberRead])
def list_members(
    ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_read_uow)
) -> list[ids.ProjectMemberRead]:
    ctx.require("project.view")
    return [
        ids.ProjectMemberRead(
            user=ids.UserRef(**vars(m.user)),
            role=ids.RoleBrief(code=m.role_code, name=m.role_name),
            granted_at=m.granted_at,
        )
        for m in identity_queries.project_members(uow.session, ctx.principal.organization_id, ctx.pid)
    ]


@router.get("/projects/{project_id}/member-candidates", response_model=list[ids.UserRef])
def member_candidates(
    ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_read_uow)
) -> list[ids.UserRef]:
    """Active organization users who can be added (needs project.members.manage, not org.users.manage)."""
    ctx.require("project.members.manage")
    return [
        ids.UserRef(**vars(u))
        for u in identity_queries.member_candidates(uow.session, ctx.principal.organization_id, ctx.pid)
    ]


def _member_read(uow: UnitOfWork, ctx: AccessContext, user_id: UUID) -> ids.ProjectMemberRead:
    for m in identity_queries.project_members(uow.session, ctx.principal.organization_id, ctx.pid):
        if m.user.id == user_id:
            return ids.ProjectMemberRead(
                user=ids.UserRef(**vars(m.user)),
                role=ids.RoleBrief(code=m.role_code, name=m.role_name),
                granted_at=m.granted_at,
            )
    raise NotFound()


@router.post(
    "/projects/{project_id}/members",
    response_model=ids.ProjectMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    body: ids.MemberAdd, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_uow)
) -> ids.ProjectMemberRead:
    """US-024, BR-29 (default Viewer)."""
    identity.add_member(uow, ctx, user_id=body.user_id, role_code=body.role_code)
    return _member_read(uow, ctx, body.user_id)


@router.patch("/projects/{project_id}/members/{user_id}", response_model=ids.ProjectMemberRead)
def change_member(
    user_id: UUID,
    body: ids.MemberPatch,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_uow),
) -> ids.ProjectMemberRead:
    identity.change_member_role(uow, ctx, user_id=user_id, role_code=body.role_code)
    return _member_read(uow, ctx, user_id)


@router.delete("/projects/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: UUID, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_uow)
) -> None:
    identity.remove_member(uow, ctx, user_id=user_id)


# -- environments ---------------------------------------------------------------------------------


def _env_read(e: Any) -> ws.EnvironmentRead:
    return ws.EnvironmentRead(
        id=e.id,
        project_id=e.project_id,
        name=e.name,
        description=e.description,
        archived=e.archived_at is not None,
        archived_at=e.archived_at,
        row_version=e.row_version,
    )


@router.get("/projects/{project_id}/environments", response_model=list[ws.EnvironmentRead])
def list_environments(
    include_archived: bool = False,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> list[ws.EnvironmentRead]:
    """Archived environments are excluded unless asked for (AC-WS-03: not selectable for new cycles)."""
    ctx.require("project.view")
    return [
        _env_read(e)
        for e in workspace_queries.environments(
            uow.session,
            ctx.principal.organization_id,
            ctx.pid,
            include_archived=include_archived,
        )
    ]


@router.post(
    "/projects/{project_id}/environments",
    response_model=ws.EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_environment(
    body: ws.EnvironmentCreate,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_uow),
) -> ws.EnvironmentRead:
    return _env_read(workspace.create_environment(uow, ctx, name=body.name, description=body.description))


@router.patch("/environments/{environment_id}", response_model=ws.EnvironmentRead)
def patch_environment(
    environment_id: UUID,
    body: ws.EnvironmentPatch,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = Depends(project_context_from("environment", "environment_id")),
    uow: UnitOfWork = Depends(get_uow),
) -> ws.EnvironmentRead:
    env = workspace.update_environment(
        uow,
        ctx,
        environment_id,
        row_version=resolve_row_version(body.row_version, if_match),
        name=body.name,
        description=body.description,
        description_set="description" in body.model_fields_set,
    )
    _etag(response, env.row_version)
    return _env_read(env)


@router.post("/environments/{environment_id}/archive", response_model=ws.EnvironmentRead)
def archive_environment(
    environment_id: UUID,
    ctx: AccessContext = Depends(project_context_from("environment", "environment_id")),
    uow: UnitOfWork = Depends(get_uow),
) -> ws.EnvironmentRead:
    return _env_read(workspace.set_environment_archived(uow, ctx, environment_id, archived=True))


@router.post("/environments/{environment_id}/restore", response_model=ws.EnvironmentRead)
def restore_environment(
    environment_id: UUID,
    ctx: AccessContext = Depends(project_context_from("environment", "environment_id")),
    uow: UnitOfWork = Depends(get_uow),
) -> ws.EnvironmentRead:
    return _env_read(workspace.set_environment_archived(uow, ctx, environment_id, archived=False))


# -- releases -------------------------------------------------------------------------------------


def _release_read(r: Any) -> ws.ReleaseRead:
    return ws.ReleaseRead(
        id=r.id,
        project_id=r.project_id,
        name=r.name,
        description=r.description,
        status=r.status,
        start_date=r.start_date,
        target_date=r.target_date,
        released_at=r.released_at,
        allowed_transitions=workspace_queries.allowed_release_targets(r),
        row_version=r.row_version,
    )


@router.get("/projects/{project_id}/releases", response_model=list[ws.ReleaseRead])
def list_releases(
    ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_read_uow)
) -> list[ws.ReleaseRead]:
    ctx.require("project.view")
    return [
        _release_read(r)
        for r in workspace_queries.releases(uow.session, ctx.principal.organization_id, ctx.pid)
    ]


@router.post(
    "/projects/{project_id}/releases", response_model=ws.ReleaseRead, status_code=status.HTTP_201_CREATED
)
def create_release(
    body: ws.ReleaseCreate, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_uow)
) -> ws.ReleaseRead:
    return _release_read(
        workspace.create_release(
            uow,
            ctx,
            name=body.name,
            description=body.description,
            start_date=body.start_date,
            target_date=body.target_date,
        )
    )


@router.get("/releases/{release_id}", response_model=ws.ReleaseRead)
def get_release(
    release_id: UUID,
    response: Response,
    ctx: AccessContext = Depends(project_context_from("release", "release_id")),
    uow: UnitOfWork = Depends(get_read_uow),
) -> ws.ReleaseRead:
    ctx.require("project.view")
    r = workspace_queries.release(uow.session, ctx.principal.organization_id, release_id)
    if r is None:
        raise NotFound()
    _etag(response, r.row_version)
    return _release_read(r)


@router.patch("/releases/{release_id}", response_model=ws.ReleaseRead)
def patch_release(
    release_id: UUID,
    body: ws.ReleasePatch,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = Depends(project_context_from("release", "release_id")),
    uow: UnitOfWork = Depends(get_uow),
) -> ws.ReleaseRead:
    """US-026 / TCMS-024: status changes follow the transition table (docs/02 §4.4)."""
    fields = {k: getattr(body, k) for k in body.model_fields_set if k != "row_version"}
    r = workspace.update_release(
        uow, ctx, release_id, row_version=resolve_row_version(body.row_version, if_match), fields=fields
    )
    _etag(response, r.row_version)
    return _release_read(r)
