"""Global search (docs/02 §12, docs/06 §4.11; US-130; ADR-022 PostgreSQL search)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from tcms.api.deps import Auth, get_read_uow, request_meta
from tcms.bugs import queries as bug_queries
from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.enums import ProjectStatus
from tcms.core.errors import NotFound
from tcms.core.uow import UnitOfWork
from tcms.execution import queries as exec_queries
from tcms.identity import queries as identity_queries
from tcms.identity.service import Authenticated
from tcms.planning import queries as plan_queries
from tcms.requirements import queries as req_queries
from tcms.testdesign import queries as td_queries
from tcms.workspace import queries as workspace_queries

router = APIRouter(prefix="/api/v1", tags=["search"])

SearchType = Literal["test_case", "folder", "plan", "cycle", "requirement", "bug"]
ALL_TYPES: tuple[SearchType, ...] = ("test_case", "requirement", "bug", "cycle", "plan", "folder")


class SearchProject(BaseModel):
    id: UUID
    key: str


class SearchItem(BaseModel):
    type: SearchType
    id: str = Field(description="Record id, or the reference for bugs")
    key: str = Field(description="Key, reference or folder name")
    title: str | None
    url: str | None = Field(default=None, description="Tracker URL (requirements, bugs)")
    project: SearchProject


class SearchGroup(BaseModel):
    type: SearchType
    items: list[SearchItem]


class SearchRead(BaseModel):
    q: str
    groups: list[SearchGroup]


def _contexts(
    uow: UnitOfWork, auth: Authenticated, meta: RequestMeta, project_id: UUID | None
) -> list[tuple[AccessContext, SearchProject]]:
    """Projects the caller may read: the given one, or every active project they belong to."""
    memberships = {m.project_id: m for m in identity_queries.memberships(uow.session, auth)}
    ids = {project_id} if project_id else set(memberships)
    projects = workspace_queries.projects(uow.session, auth.organization_id, ids=ids, status=None)
    out = []
    principal = Principal(
        auth.user_id, auth.organization_id, auth.is_org_admin, display_name=auth.display_name
    )
    for p in projects:
        m = memberships.get(p.id)
        if m is None and not auth.is_org_admin:
            continue
        if project_id is None and p.status != ProjectStatus.active:
            continue
        perms = frozenset(m.permissions) if m else frozenset({"project.view"})
        if "project.view" not in perms:
            continue
        ctx = AccessContext.for_principal(principal, meta, project_id=p.id, permissions=perms)
        out.append((ctx, SearchProject(id=p.id, key=p.key)))
    if project_id is not None and not out:
        raise NotFound()
    return out


@router.get("/search", response_model=SearchRead)
def search(
    q: str = Query(min_length=1, max_length=100),
    project_id: UUID | None = Query(default=None, description="Omit to search all my projects"),
    types: str | None = Query(default=None, description="Comma list; default all"),
    limit: int = Query(default=5, ge=1, le=50),
    auth: Authenticated = Auth,
    meta: RequestMeta = Depends(request_meta),
    uow: UnitOfWork = Depends(get_read_uow),
) -> SearchRead:
    """US-130 / TCMS-118/119: exact keys first, then text; grouped by type, `limit` per group."""
    wanted = [t for t in ALL_TYPES if not types or t in {x.strip() for x in types.split(",")}]
    groups: dict[SearchType, list[SearchItem]] = {t: [] for t in wanted}
    s = uow.session
    term = q.strip()
    for ctx, proj in _contexts(uow, auth, meta, project_id):
        if "test_case" in groups:
            for h in td_queries.search_cases(s, ctx, term, limit):
                groups["test_case"].append(
                    SearchItem(type="test_case", id=str(h.id), key=h.key, title=h.title, project=proj)
                )
        if "requirement" in groups:
            for r in req_queries.search(s, ctx, term, limit):
                groups["requirement"].append(
                    SearchItem(
                        type="requirement",
                        id=str(r.id),
                        key=r.reference,
                        title=r.title,
                        url=r.url,
                        project=proj,
                    )
                )
        if "bug" in groups:
            for b in bug_queries.bug_list(s, ctx, q=term, cycle_id=None, failing=False)[:limit]:
                groups["bug"].append(
                    SearchItem(
                        type="bug", id=b.reference, key=b.reference, title=b.title, url=b.url, project=proj
                    )
                )
        if "cycle" in groups:
            for c in exec_queries.search_cycles(s, ctx, term, limit):
                groups["cycle"].append(
                    SearchItem(type="cycle", id=str(c.id), key=c.key, title=c.name, project=proj)
                )
        if "plan" in groups:
            for p in plan_queries.search_plans(s, ctx, term, limit):
                groups["plan"].append(
                    SearchItem(type="plan", id=str(p.id), key=p.key, title=p.name, project=proj)
                )
        if "folder" in groups:
            for f in td_queries.search_folders(s, ctx, term, limit):
                groups["folder"].append(
                    SearchItem(type="folder", id=str(f.id), key=f.key, title=f.title, project=proj)
                )
    return SearchRead(
        q=term,
        groups=[SearchGroup(type=t, items=items[:limit]) for t, items in groups.items() if items],
    )
