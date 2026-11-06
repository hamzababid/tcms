"""Saved views (docs/06 §4.11; docs/02 §12; US-132)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from tcms.api.deps import get_read_uow, get_uow, project_context, project_context_from
from tcms.core.context import AccessContext
from tcms.core.enums import ViewVisibility
from tcms.core.uow import UnitOfWork
from tcms.platform import saved_views as views

router = APIRouter(prefix="/api/v1", tags=["saved-views"])

ViewCtx = Depends(project_context_from("saved_view", "view_id"))


class ViewDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: dict[str, str] = Field(default_factory=dict, description="The list's query parameters")
    sort: str | None = None
    columns: list[str] | None = Field(default=None, description="Visible column ids, in order")


class SavedViewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(description="test_case, test_run, test_plan, test_cycle, bug, requirement")
    name: str = Field(min_length=1, max_length=100)
    visibility: ViewVisibility = ViewVisibility.private
    definition: ViewDefinition
    is_default: bool = False


class SavedViewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    visibility: ViewVisibility | None = None
    definition: ViewDefinition | None = None
    is_default: bool | None = None


class SavedViewRead(BaseModel):
    id: UUID
    entity_type: str
    name: str
    visibility: ViewVisibility
    definition: ViewDefinition
    is_default: bool
    mine: bool
    updated_at: datetime
    row_version: int


def _read(v: Any, ctx: AccessContext) -> SavedViewRead:
    return SavedViewRead(
        id=v.id,
        entity_type=v.entity_type,
        name=v.name,
        visibility=v.visibility,
        definition=ViewDefinition(**v.definition),
        is_default=v.is_default,
        mine=v.owner_id == ctx.principal.user_id,
        updated_at=v.updated_at,
        row_version=v.row_version,
    )


@router.get("/projects/{project_id}/saved-views", response_model=list[SavedViewRead])
def list_saved_views(
    entity_type: str | None = Query(default=None, max_length=40),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> list[SavedViewRead]:
    """Mine and shared; the first `is_default` entry is the view to open the list with."""
    ctx.require("project.view")
    return [_read(v, ctx) for v in views.list_views(uow, ctx, entity_type)]


@router.post(
    "/projects/{project_id}/saved-views", response_model=SavedViewRead, status_code=status.HTTP_201_CREATED
)
def create_saved_view(
    body: SavedViewCreate, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_uow)
) -> SavedViewRead:
    v = views.create(
        uow,
        ctx,
        entity_type=body.entity_type,
        name=body.name,
        visibility=body.visibility,
        definition=body.definition.model_dump(),
        is_default=body.is_default,
    )
    return _read(v, ctx)


@router.patch("/saved-views/{view_id}", response_model=SavedViewRead)
def patch_saved_view(
    view_id: UUID, body: SavedViewPatch, ctx: AccessContext = ViewCtx, uow: UnitOfWork = Depends(get_uow)
) -> SavedViewRead:
    fields: dict[str, Any] = {}
    for k in body.model_fields_set:
        value = getattr(body, k)
        if value is None:
            continue
        fields[k] = value.model_dump() if isinstance(value, ViewDefinition) else value
    return _read(views.update_view(uow, ctx, view_id, fields=fields), ctx)


@router.delete("/saved-views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_view(
    view_id: UUID, ctx: AccessContext = ViewCtx, uow: UnitOfWork = Depends(get_uow)
) -> Response:
    views.delete_view(uow, ctx, view_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
