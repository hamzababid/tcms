"""Comments and attachments on any record (docs/06 §4.12, docs/02 §9)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from tcms.api.deps import (
    Auth,
    ReadUow,
    Uow,
    app_state,
    project_context_for,
    project_context_from,
)
from tcms.core.context import AccessContext
from tcms.core.errors import NotFound
from tcms.core.uow import UnitOfWork
from tcms.execution import service as execution
from tcms.identity import queries as identity_queries
from tcms.identity.schemas import UserRef
from tcms.identity.service import Authenticated
from tcms.platform import attachments, comments
from tcms.platform.records import RecordRef
from tcms.testdesign import schemas as s
from tcms.testdesign import service as testdesign
from tcms.workspace import queries as workspace_queries

router = APIRouter(prefix="/api/v1", tags=["records"])

CommentEntity = Literal["test_case", "test_case_version"]
AttachmentEntity = Literal["test_case", "test_case_step", "test_step_result"]


def _record(uow: UnitOfWork, ctx: AccessContext, entity_type: str, entity_id: UUID) -> RecordRef:
    if entity_type == "test_step_result":  # evidence on a step of an attempt (M4)
        return execution.step_result_record(uow, ctx, entity_id)
    return testdesign.resolve_record(uow, ctx, entity_type, entity_id)


def _members(uow: UnitOfWork, ctx: AccessContext) -> set[UUID]:
    return {
        m.user.id
        for m in identity_queries.project_members(uow.session, ctx.principal.organization_id, ctx.pid)
    }


def _comment_read(c: comments.CommentRow, refs: dict[UUID, UserRef]) -> s.CommentRead:
    return s.CommentRead(
        id=c.id,
        entity_type=c.entity_type,
        entity_id=c.entity_id,
        body=c.body,
        mentions=c.mentions,
        author=refs.get(c.created_by),
        created_at=c.created_at,
        edited_at=c.edited_at,
        deleted=c.deleted,
        editable_until=c.editable_until,
    )


def _refs(uow: UnitOfWork, ids_: set[UUID]) -> dict[UUID, UserRef]:
    return {k: UserRef(**vars(v)) for k, v in identity_queries.user_refs(uow.session, ids_).items()}


# -- comments -------------------------------------------------------------------------------------


@router.get("/comments", response_model=list[s.CommentRead])
def list_comments(
    request: Request,
    entity_type: CommentEntity,
    entity_id: UUID,
    auth: Authenticated = Auth,
    uow: UnitOfWork = ReadUow,
) -> list[s.CommentRead]:
    """Oldest first; deleted comments keep their place with `body: null` (FR-COL-001)."""
    ctx = project_context_for(request, auth, entity_type, entity_id)
    rows = comments.list_comments(uow, ctx, _record(uow, ctx, entity_type, entity_id))
    refs = _refs(uow, {c.created_by for c in rows})
    return [_comment_read(c, refs) for c in rows]


@router.post("/comments", response_model=s.CommentRead, status_code=status.HTTP_201_CREATED)
def add_comment(
    body: s.CommentCreate, request: Request, auth: Authenticated = Auth, uow: UnitOfWork = Uow
) -> s.CommentRead:
    """Mentions use `@[Name](user:<uuid>)`; only project members are notified."""
    ctx = project_context_for(request, auth, body.entity_type, body.entity_id)
    record = _record(uow, ctx, body.entity_type, body.entity_id)
    row = comments.add_comment(uow, ctx, record, body.body, members=_members(uow, ctx))
    return _comment_read(row, _refs(uow, {row.created_by}))


@router.patch("/comments/{comment_id}", response_model=s.CommentRead)
def edit_comment(
    comment_id: UUID,
    body: s.CommentPatch,
    ctx: AccessContext = Depends(project_context_from("comment", "comment_id")),
    uow: UnitOfWork = Uow,
) -> s.CommentRead:
    """Author only, within 15 minutes."""
    row = comments.edit_comment(uow, ctx, comment_id, body.body, members=_members(uow, ctx))
    return _comment_read(row, _refs(uow, {row.created_by}))


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: UUID,
    ctx: AccessContext = Depends(project_context_from("comment", "comment_id")),
    uow: UnitOfWork = Uow,
) -> None:
    comments.delete_comment(uow, ctx, comment_id)


# -- attachments ----------------------------------------------------------------------------------

# Served files never run script or load anything (docs/03 §9).
CONTENT_CSP = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
AttachmentCtx = Depends(project_context_from("attachment", "attachment_id"))


def attachment_read(a: attachments.AttachmentRow, refs: dict[UUID, UserRef]) -> s.AttachmentRead:
    return s.AttachmentRead(
        id=a.id,
        file_name=a.file_name,
        content_type=a.content_type,
        size_bytes=a.size_bytes,
        uploaded_by=refs.get(a.uploaded_by),
        uploaded_at=a.uploaded_at,
        entity_type=a.entity_type,
        entity_id=a.entity_id,
        url=f"/api/v1/attachments/{a.id}/content",
    )


def _store(request: Request) -> attachments.Storage:
    store = app_state(request).store
    if store is None:  # pragma: no cover - create_app always configures it
        raise RuntimeError("attachment storage is not configured")
    return store


@router.post("/attachments", response_model=s.AttachmentRead, status_code=status.HTTP_201_CREATED)
def upload(
    request: Request,
    file: UploadFile = File(),
    entity_type: AttachmentEntity = Form(),
    entity_id: UUID = Form(),
    auth: Authenticated = Auth,
    uow: UnitOfWork = Uow,
) -> s.AttachmentRead:
    """Limit: the project's `attachment_max_mb` (≤ org cap); type is sniffed, not trusted (docs/02 §9.2)."""
    ctx = project_context_for(request, auth, entity_type, entity_id)
    record = _record(uow, ctx, entity_type, entity_id)
    project = workspace_queries.project(uow.session, ctx.principal.organization_id, ctx.pid)
    if project is None:
        raise NotFound()
    max_mb = int(workspace_queries.project_settings(project)["attachment_max_mb"])
    row = attachments.upload(
        uow,
        ctx,
        record,
        file.file,
        file.filename or "file",
        max_bytes=max_mb * 1024 * 1024,
        store=_store(request),
    )
    return attachment_read(row, _refs(uow, {row.uploaded_by}))


def _attachment(uow: UnitOfWork, ctx: AccessContext, attachment_id: UUID) -> attachments.AttachmentRow:
    ctx.require("project.view")
    row = attachments.metadata(uow, ctx.principal.organization_id, attachment_id)
    if row is None:
        raise NotFound()
    return row


@router.get("/attachments/{attachment_id}", response_model=s.AttachmentRead)
def get_attachment(
    attachment_id: UUID, ctx: AccessContext = AttachmentCtx, uow: UnitOfWork = ReadUow
) -> s.AttachmentRead:
    row = _attachment(uow, ctx, attachment_id)
    return attachment_read(row, _refs(uow, {row.uploaded_by}))


@router.get(
    "/attachments/{attachment_id}/content",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/octet-stream": {}}, "description": "The file"}},
)
def attachment_content(
    request: Request,
    attachment_id: UUID,
    download: bool = Query(default=False, description="Force `Content-Disposition: attachment`"),
    ctx: AccessContext = AttachmentCtx,
    uow: UnitOfWork = ReadUow,
) -> StreamingResponse:
    """Images and PDFs inline, everything else as a download; always sandboxed (docs/03 §9)."""
    att = _attachment(uow, ctx, attachment_id)
    body, disposition = attachments.open_object(_store(request), uow, att.id)
    if download:
        disposition = "attachment"
    return StreamingResponse(
        body.iter_chunks(),  # type: ignore[attr-defined]
        media_type=att.content_type,
        headers={
            "Content-Disposition": attachments.content_disposition(disposition, att.file_name),
            "Content-Length": str(att.size_bytes),
            "Content-Security-Policy": CONTENT_CSP,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.delete(
    "/attachments/{attachment_id}/links/{entity_type}/{entity_id}", status_code=status.HTTP_204_NO_CONTENT
)
def unlink(
    attachment_id: UUID,
    entity_type: AttachmentEntity,
    entity_id: UUID,
    ctx: AccessContext = AttachmentCtx,
    uow: UnitOfWork = Uow,
) -> None:
    """Uploader or holder of the record's write permission; BR-28 blocks approved step evidence."""
    attachments.unlink(uow, ctx, attachment_id, _record(uow, ctx, entity_type, entity_id))
