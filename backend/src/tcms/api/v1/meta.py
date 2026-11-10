"""Meta and record-history endpoints (docs/06 §4.12, §4.14)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from tcms.api.deps import (
    Auth,
    ReadUow,
)
from tcms.core.enums import PG_TYPES
from tcms.core.errors import NotFound
from tcms.core.pagination import Page, PageParams
from tcms.core.permissions import CATALOG, RESERVED_P2
from tcms.core.uow import UnitOfWork
from tcms.identity import queries as identity_queries
from tcms.identity.service import Authenticated
from tcms.platform.audit import queries as audit_queries
from tcms.workspace import schemas as ws

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/meta/enums", response_model=dict[str, list[str]])
def enums(_: Authenticated = Auth) -> dict[str, list[str]]:
    return {name: [m.value for m in cls] for name, cls in sorted(PG_TYPES.items())}


@router.get("/meta/permissions", response_model=list[ws.PermissionRead])
def permissions(_: Authenticated = Auth) -> list[ws.PermissionRead]:
    return [
        ws.PermissionRead(permission=p, scope=scope.value)
        for p, scope in sorted(CATALOG.items())
        if p not in RESERVED_P2
    ]


@router.get("/audit-events/entity/{entity_type}/{entity_id}", response_model=Page[ws.ActivityItem])
def record_history(
    entity_type: str,
    entity_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: Authenticated = Auth,
    uow: UnitOfWork = ReadUow,
) -> Page[ws.ActivityItem]:
    """US-161: a record's history. Project records need `project.view`; org-level ones `org.audit.view`."""
    s = uow.session
    projects = audit_queries.entity_projects(s, auth.organization_id, entity_type, entity_id)
    if not projects:
        raise NotFound()
    for project_id in projects:
        if project_id is None:
            if "org.audit.view" not in identity_queries.org_permissions(s, auth):
                raise NotFound()
        else:
            perms = identity_queries.project_permissions(s, auth, project_id)
            if perms is None or "project.view" not in perms:
                raise NotFound()
    rows, total = audit_queries.entity_history(
        s, auth.organization_id, entity_type, entity_id, PageParams(page=page, page_size=page_size)
    )
    return Page[ws.ActivityItem](
        items=[ws.ActivityItem.model_validate(vars(r)) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )
