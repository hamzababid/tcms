"""Folders, test cases, versions, review, tags, bulk (docs/06 §4.4)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse

from tcms.api.deps import (
    app_state,
    get_read_uow,
    get_uow,
    project_context,
    project_context_from,
    resolve_row_version,
)
from tcms.api.idempotency import Idempotency, idempotency
from tcms.core import ids
from tcms.core.context import AccessContext
from tcms.core.errors import NotFound, ValidationFailed
from tcms.core.pagination import Page, PageParams
from tcms.core.uow import UnitOfWork
from tcms.execution import queries as execution_queries
from tcms.identity import queries as identity_queries
from tcms.identity.schemas import UserRef
from tcms.platform import attachments
from tcms.platform.audit import queries as audit_queries
from tcms.testdesign import queries as tq
from tcms.testdesign import rules, service
from tcms.testdesign import schemas as s
from tcms.testdesign.jobs import job_payload
from tcms.workspace import schemas as ws


def requirement_restrict(
    uow: UnitOfWork, ctx: AccessContext, params: Mapping[str, Any]
) -> tq.Restrict | None:
    """Repository filters `requirement` and `has_requirements` (L19, ADR-024), resolved here because the
    requirements module sits above testdesign."""
    from tcms.requirements import queries as rq

    ref = str(params.get("requirement") or "").strip()
    if ref:
        return (rq.case_ids_with_reference(uow.session, ctx, ref), True)
    has = str(params.get("has_requirements") or "").lower()
    if has in ("true", "false"):
        return (rq.linked_case_ids_stmt(ctx), has == "true")
    return None


router = APIRouter(prefix="/api/v1", tags=["test-cases"])

CaseCtx = Depends(project_context_from("test_case", "case_id"))
FolderCtx = Depends(project_context_from("folder", "folder_id"))


def _etag(response: Response, rv: int) -> None:
    response.headers["ETag"] = f'"{rv}"'


def _refs(uow: UnitOfWork, ids_: set[UUID | None]) -> dict[UUID, UserRef]:
    found = identity_queries.user_refs(uow.session, {i for i in ids_ if i is not None})
    return {k: UserRef(**vars(v)) for k, v in found.items()}


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


def version_read(
    uow: UnitOfWork, ctx: AccessContext, v: tq.VersionView, refs: dict[UUID, UserRef]
) -> s.VersionRead:
    step_atts = attachments.list_for(
        uow, ctx.principal.organization_id, "test_case_step", [st.id for st in v.steps]
    )
    return s.VersionRead(
        id=v.id,
        version_no=v.version_no,
        format=v.format,
        title=v.title,
        description=v.description,
        preconditions=v.preconditions,
        test_data=v.test_data,
        expected_result=v.expected_result,
        postconditions=v.postconditions,
        text_body=v.text_body,
        change_note=v.change_note,
        created_by=refs.get(v.created_by),
        created_at=v.created_at,
        submission=s.Submission(
            submitted_by=refs.get(v.submitted_by) if v.submitted_by else None, submitted_at=v.submitted_at
        )
        if v.submitted_at
        else None,
        approval=s.Approval(
            mode=v.approval_mode,
            approved_by=refs.get(v.approved_by) if v.approved_by else None,
            approved_at=v.approved_at,
        )
        if v.approved_at and v.approval_mode
        else None,
        steps=[
            s.StepRead(
                id=st.id,
                position=st.position,
                action=st.action,
                expected_result=st.expected_result,
                data=st.data,
                attachments=[attachment_read(a, refs) for a in step_atts.get(st.id, [])],
            )
            for st in v.steps
        ],
    )


def case_read(
    uow: UnitOfWork,
    ctx: AccessContext,
    case_id: UUID,
    *,
    version_no: int | None = None,
    warnings: list[str] | None = None,
) -> s.CaseRead:
    from tcms.platform import comments

    d = tq.case_detail(uow.session, ctx, case_id, version_no=version_no)
    c, v = d.case, d.version
    case_atts = attachments.list_for(uow, ctx.principal.organization_id, "test_case", [c.id])[c.id]
    people = {
        c.owner_id,
        c.reviewer_id,
        c.created_by,
        v.created_by,
        v.approved_by,
        v.submitted_by,
        *(a.uploaded_by for a in case_atts),
    }
    refs = _refs(uow, people)
    step_refs = _refs(
        uow,
        {
            a.uploaded_by
            for lst in attachments.list_for(
                uow, ctx.principal.organization_id, "test_case_step", [st.id for st in v.steps]
            ).values()
            for a in lst
        },
    )
    refs.update(step_refs)
    record = service.case_record(c)
    n_comments = len(comments.list_comments(uow, ctx, record))
    return s.CaseRead(
        id=c.id,
        key=c.key,
        project_id=c.project_id,
        folder=s.FolderRef(
            id=c.folder_id, name=d.folder_path[-1] if d.folder_path else "", path_names=d.folder_path
        ),
        title=c.title,
        type=c.type,
        design_technique=c.design_technique,
        priority=c.priority,
        status=c.status,
        format=c.format,
        owner=refs.get(c.owner_id),
        reviewer=refs.get(c.reviewer_id) if c.reviewer_id else None,
        automation_status=c.automation_status,
        automation_keys=d.automation_keys,
        estimated_minutes=c.estimated_minutes,
        tags=d.summary.tags,
        latest_version_no=c.latest_version_no,
        approved_version_no=d.summary.approved_version_no,
        version=version_read(uow, ctx, v, refs),
        links=[
            s.CaseLinkRead(
                case_id=lk.case_id,
                key=lk.key,
                title=lk.title,
                status=lk.status,
                link_type=lk.link_type,
                direction=lk.direction,
            )
            for lk in d.links
        ],
        attachments=[attachment_read(a, refs) for a in case_atts],
        counts=s.CaseCounts(attachments=len(case_atts), comments=n_comments, versions=c.latest_version_no),
        warnings=sorted({*(warnings or []), *(["title_exists"] if d.title_exists_in_folder else [])}),
        created_by=refs.get(c.created_by) if c.created_by else None,
        created_at=c.created_at,
        updated_at=c.updated_at,
        row_version=c.row_version,
    )


def _content(body: s.ContentIn) -> rules.Content:
    return rules.Content(
        format=body.format,
        title=body.title,
        description=body.description,
        preconditions=body.preconditions,
        test_data=body.test_data,
        expected_result=body.expected_result,
        postconditions=body.postconditions,
        text_body=body.text_body,
        steps=tuple(rules.StepContent(x.action, x.expected_result, x.data) for x in body.steps),
    )


# -- folders --------------------------------------------------------------------------------------


def _folder_read(n: tq.FolderNode) -> s.FolderRead:
    return s.FolderRead(**vars(n))


@router.get("/projects/{project_id}/folders", response_model=list[s.FolderRead])
def list_folders(
    include_archived: bool = False,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> list[s.FolderRead]:
    """US-043: full tree with counts including descendants."""
    ctx.require("project.view")
    return [_folder_read(n) for n in tq.folder_tree(uow.session, ctx, include_archived=include_archived)]


def _node(uow: UnitOfWork, ctx: AccessContext, folder_id: UUID) -> s.FolderRead:
    for n in tq.folder_tree(uow.session, ctx, include_archived=True):
        if n.id == folder_id:
            return _folder_read(n)
    raise NotFound()


@router.post(
    "/projects/{project_id}/folders", response_model=s.FolderRead, status_code=status.HTTP_201_CREATED
)
def create_folder(
    body: s.FolderCreate,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_uow),
    guard: Idempotency = Depends(idempotency("create_folder")),
) -> Any:
    if (replay := guard.replay(body)) is not None:
        return replay
    f = service.create_folder(
        uow, ctx, name=body.name, parent_id=body.parent_id, description=body.description
    )
    uow.session.flush()
    result = _node(uow, ctx, f.id)
    guard.store(201, result)
    return result


@router.patch("/folders/{folder_id}", response_model=s.FolderRead)
def patch_folder(
    folder_id: UUID,
    body: s.FolderPatch,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = FolderCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.FolderRead:
    service.update_folder(
        uow,
        ctx,
        folder_id,
        row_version=resolve_row_version(body.row_version, if_match),
        name=body.name,
        description=body.description,
        description_set="description" in body.model_fields_set,
    )
    uow.session.flush()
    return _node(uow, ctx, folder_id)


@router.post("/folders/{folder_id}/move", response_model=s.FolderRead)
def move_folder(
    folder_id: UUID,
    body: s.FolderMove,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = FolderCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.FolderRead:
    """AC-TD-01/02."""
    service.move_folder(
        uow,
        ctx,
        folder_id,
        row_version=resolve_row_version(body.row_version, if_match),
        parent_id=body.parent_id,
        position=body.position,
    )
    uow.session.flush()
    return _node(uow, ctx, folder_id)


@router.post("/folders/{folder_id}/archive", response_model=s.FolderRead)
def archive_folder(
    folder_id: UUID, ctx: AccessContext = FolderCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.FolderRead:
    service.set_folder_archived(uow, ctx, folder_id, archived=True)
    uow.session.flush()
    return _node(uow, ctx, folder_id)


@router.post("/folders/{folder_id}/restore", response_model=s.FolderRead)
def restore_folder(
    folder_id: UUID, ctx: AccessContext = FolderCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.FolderRead:
    service.set_folder_archived(uow, ctx, folder_id, archived=False)
    uow.session.flush()
    return _node(uow, ctx, folder_id)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    folder_id: UUID, ctx: AccessContext = FolderCtx, uow: UnitOfWork = Depends(get_uow)
) -> None:
    """BR-15 / AC-TD-03."""
    service.delete_folder(uow, ctx, folder_id)


# -- cases ----------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/test-cases", response_model=Page[s.CaseListItem])
def list_cases(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    folder_id: UUID | None = None,
    include_subfolders: bool = True,
    include_archived: bool = False,
    status_: str | None = Query(default=None, alias="status"),
    type_: str | None = Query(default=None, alias="type"),
    priority: str | None = None,
    owner_id: UUID | None = None,
    reviewer_id: UUID | None = None,
    tag: str | None = None,
    automation_status: str | None = None,
    updated_at__gte: datetime | None = None,
    updated_at__lte: datetime | None = None,
    requirement: str | None = Query(default=None, max_length=100, description="Linked to this reference"),
    has_requirements: bool | None = Query(
        default=None, description="With (true) or without (false) references"
    ),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> Page[s.CaseListItem]:
    """US-043 / FR-SRCH-002: filters and sorts of docs/06 §4.4 (operators per §2.6)."""
    ctx.require("project.view")
    params = dict(request.query_params)
    rows, total = tq.list_cases(
        uow.session,
        ctx,
        params,
        PageParams(page=page, page_size=page_size),
        restrict=requirement_restrict(uow, ctx, params),
    )
    refs = _refs(uow, {r.owner_id for r in rows})
    return Page[s.CaseListItem](
        items=[
            s.CaseListItem(
                id=r.id,
                key=r.key,
                title=r.title,
                folder_id=r.folder_id,
                type=r.type,
                priority=r.priority,
                status=r.status,
                format=r.format,
                owner=refs.get(r.owner_id),
                automation_status=r.automation_status,
                latest_version_no=r.latest_version_no,
                approved_version_no=r.approved_version_no,
                tags=r.tags,
                updated_at=r.updated_at,
                row_version=r.row_version,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/projects/{project_id}/test-cases", response_model=s.SaveResponse, status_code=status.HTTP_201_CREATED
)
def create_case(
    body: s.CaseCreate,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_uow),
    guard: Idempotency = Depends(idempotency("create_case")),
) -> Any:
    """US-050/051: version 1, key allocated (TCMS-033)."""
    if (replay := guard.replay(body)) is not None:
        return replay
    meta = service.CaseMetadata(
        folder_id=body.folder_id,
        type=body.type,
        design_technique=body.design_technique,
        priority=body.priority,
        tags=body.tags,
        owner_id=body.owner_id,
        reviewer_id=body.reviewer_id,
        automation_status=body.automation_status,
        automation_keys=body.automation_keys,
        estimated_minutes=body.estimated_minutes,
    )
    result = service.create_case(uow, ctx, content=_content(body.content), meta=meta)
    uow.session.flush()
    out = s.SaveResponse(
        case=case_read(uow, ctx, result.case.id, warnings=result.warnings), version_created=True
    )
    guard.store(201, out)
    return out


@router.get("/test-cases/{case_id}", response_model=s.CaseRead)
def get_case(
    case_id: UUID,
    response: Response,
    version: int | None = Query(default=None, ge=1),
    ctx: AccessContext = CaseCtx,
    uow: UnitOfWork = Depends(get_read_uow),
) -> s.CaseRead:
    ctx.require("project.view")
    out = case_read(uow, ctx, case_id, version_no=version)
    _etag(response, out.row_version)
    return out


@router.patch("/test-cases/{case_id}", response_model=s.CaseRead)
def patch_case(
    case_id: UUID,
    body: s.CasePatch,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = CaseCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.CaseRead:
    """Metadata only (BR-01, AC-TD-10): audited, no new version."""
    fields = {k: getattr(body, k) for k in body.model_fields_set if k != "row_version"}
    service.update_metadata(
        uow, ctx, case_id, row_version=resolve_row_version(body.row_version, if_match), fields=fields
    )
    uow.session.flush()
    out = case_read(uow, ctx, case_id)
    _etag(response, out.row_version)
    return out


@router.put("/test-cases/{case_id}/content", response_model=s.SaveResponse)
def put_content(
    case_id: UUID,
    body: s.ContentUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = CaseCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.SaveResponse:
    """BR-01/02, AC-TD-11/13: a new version only when content changed (docs/04 §3.2)."""
    result = service.update_content(
        uow,
        ctx,
        case_id,
        content=_content(body.content),
        change_note=body.change_note,
        row_version=resolve_row_version(body.row_version, if_match),
    )
    uow.session.flush()
    return s.SaveResponse(case=case_read(uow, ctx, case_id), version_created=result.version_created)


@router.get("/test-cases/{case_id}/versions", response_model=list[s.VersionListItem])
def list_versions(
    case_id: UUID, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> list[s.VersionListItem]:
    """US-053 / FR-TD-004."""
    ctx.require("project.view")
    d = tq.case_detail(uow.session, ctx, case_id)
    rows = tq.versions(uow.session, ctx, case_id)
    refs = _refs(uow, {u for v in rows for u in (v.created_by, v.approved_by, v.submitted_by)})
    return [
        s.VersionListItem(
            version_no=v.version_no,
            title=v.title,
            change_note=v.change_note,
            created_by=refs.get(v.created_by),
            created_at=v.created_at,
            approval=s.Approval(
                mode=v.approval_mode.value,
                approved_by=refs.get(v.approved_by) if v.approved_by else None,
                approved_at=v.approved_at,
            )
            if v.approved_at and v.approval_mode
            else None,
            submission=s.Submission(
                submitted_by=refs.get(v.submitted_by) if v.submitted_by else None, submitted_at=v.submitted_at
            )
            if v.submitted_at
            else None,
            is_latest=v.id == d.case.latest_version_id,
            is_approved_version=v.id == d.case.approved_version_id,
        )
        for v in rows
    ]


@router.get("/test-cases/{case_id}/versions/{version_no}", response_model=s.VersionRead)
def get_version(
    case_id: UUID, version_no: int, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> s.VersionRead:
    ctx.require("project.view")
    return case_read(uow, ctx, case_id, version_no=version_no).version


@router.get("/test-cases/{case_id}/compare", response_model=s.CompareRead)
def compare(
    case_id: UUID,
    from_: int = Query(alias="from", ge=1),
    to: int = Query(ge=1),
    ctx: AccessContext = CaseCtx,
    uow: UnitOfWork = Depends(get_read_uow),
) -> s.CompareRead:
    """AC-TD-12: field diffs and steps aligned by position."""
    ctx.require("project.view")
    c = tq.compare(uow.session, ctx, case_id, from_, to)

    def step(x: rules.StepContent | None) -> s.StepContentRead | None:
        return (
            s.StepContentRead(action=x.action, expected_result=x.expected_result, data=x.data) if x else None
        )

    return s.CompareRead(
        from_version=c.from_version,
        to_version=c.to_version,
        fields=[
            s.FieldDiffRead(field=f.field, before=f.before, after=f.after, changed=f.changed)
            for f in c.fields
        ],
        steps=[
            s.StepDiffRead(position=d.position, change=d.change, before=step(d.before), after=step(d.after))
            for d in c.steps
        ],
    )


@router.post("/test-cases/{case_id}/restore-version", response_model=s.SaveResponse)
def restore_version(
    case_id: UUID,
    body: s.RestoreVersionRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = CaseCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.SaveResponse:
    """US-054 / FR-TD-005."""
    result = service.restore_version(
        uow,
        ctx,
        case_id,
        version_no=body.version_no,
        row_version=resolve_row_version(body.row_version, if_match),
    )
    uow.session.flush()
    return s.SaveResponse(case=case_read(uow, ctx, case_id), version_created=result.version_created)


@router.post("/test-cases/{case_id}/submit", response_model=s.CaseRead)
def submit(
    case_id: UUID, body: s.SubmitRequest, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CaseRead:
    """US-065."""
    service.submit_for_review(uow, ctx, case_id, reviewer_id=body.reviewer_id, comment=body.comment)
    uow.session.flush()
    return case_read(uow, ctx, case_id)


@router.post("/test-cases/{case_id}/approve", response_model=s.CaseRead)
def approve(
    case_id: UUID,
    body: s.ApproveRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = CaseCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.CaseRead:
    """US-066, AC-TD-21 (self-approval)."""
    service.approve(
        uow, ctx, case_id, row_version=resolve_row_version(body.row_version, if_match), comment=body.comment
    )
    uow.session.flush()
    return case_read(uow, ctx, case_id)


@router.post("/test-cases/{case_id}/return", response_model=s.CaseRead)
def return_case(
    case_id: UUID, body: s.ReturnRequest, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CaseRead:
    """US-066, AC-TD-22."""
    service.return_case(uow, ctx, case_id, comment=body.comment)
    uow.session.flush()
    return case_read(uow, ctx, case_id)


def _lifecycle(action: Literal["deprecate", "archive", "restore"]) -> Any:
    def endpoint(
        case_id: UUID,
        body: s.LifecycleRequest,
        ctx: AccessContext = CaseCtx,
        uow: UnitOfWork = Depends(get_uow),
    ) -> s.CaseRead:
        service.change_lifecycle(uow, ctx, case_id, action=action, reason=body.reason)
        uow.session.flush()
        return case_read(uow, ctx, case_id)

    endpoint.__name__ = f"{action}_case"
    endpoint.__doc__ = "US-068 / FR-TD-007, BR-13."
    return endpoint


for _action in ("deprecate", "archive", "restore"):
    router.add_api_route(
        f"/test-cases/{{case_id}}/{_action}", _lifecycle(_action), methods=["POST"], response_model=s.CaseRead
    )


@router.delete("/test-cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: UUID, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Depends(get_uow)) -> None:
    """US-069 / BR-14: `409 case_has_runs` once the case was in a cycle."""
    service.delete_case(uow, ctx, case_id)


@router.post(
    "/test-cases/{case_id}/duplicate", response_model=s.SaveResponse, status_code=status.HTTP_201_CREATED
)
def duplicate(
    case_id: UUID,
    body: s.DuplicateRequest,
    request: Request,
    ctx: AccessContext = CaseCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.SaveResponse:
    """US-057 / FR-TD-009 (TCMS-044)."""
    result = service.duplicate_case(
        uow, ctx, case_id, folder_id=body.folder_id, title=body.title, store=app_state(request).store
    )
    uow.session.flush()
    return s.SaveResponse(case=case_read(uow, ctx, result.case.id), version_created=True)


@router.get("/test-cases/{case_id}/executions", response_model=list[s.ExecutionRead])
def executions(
    case_id: UUID, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> list[s.ExecutionRead]:
    """US-058 / FR-TD-013: runs across cycles with the pinned version (cycles arrive in M3)."""
    ctx.require("project.view")
    rows = execution_queries.case_executions(uow.session, ctx, case_id)
    refs = _refs(uow, {r.executed_by for r in rows})
    return [
        s.ExecutionRead(
            run_id=r.run_id,
            cycle_id=r.cycle_id,
            cycle_key=r.cycle_key,
            cycle_name=r.cycle_name,
            cycle_status=r.cycle_status,
            version_no=r.version_no,
            status=r.status,
            superseded=r.superseded,
            executed_by=refs.get(r.executed_by) if r.executed_by else None,
            finished_at=r.finished_at,
        )
        for r in rows
    ]


@router.get("/test-cases/{case_id}/history", response_model=Page[ws.ActivityItem])
def history(
    case_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    actor_id: UUID | None = None,
    action: str | None = Query(default=None, max_length=100),
    occurred_at__gte: date | None = None,
    occurred_at__lte: date | None = None,
    q: str | None = Query(default=None, max_length=200),
    ctx: AccessContext = CaseCtx,
    uow: UnitOfWork = Depends(get_read_uow),
) -> Page[ws.ActivityItem]:
    """FR-AUD-002 for a case; filters as audit events (docs/06 §4.12) plus `q`."""
    ctx.require("project.view")
    rows, total = audit_queries.entity_history(
        uow.session,
        ctx.principal.organization_id,
        "test_case",
        case_id,
        PageParams(page=page, page_size=page_size),
        filters=audit_queries.AuditFilter(
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


@router.post("/test-cases/{case_id}/links", response_model=s.CaseRead)
def add_link(
    case_id: UUID, body: s.LinkRequest, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CaseRead:
    """FR-TD-012."""
    service.add_link(uow, ctx, case_id, target_case_id=body.target_case_id, link_type=body.link_type)
    uow.session.flush()
    return case_read(uow, ctx, case_id)


@router.delete("/test-cases/{case_id}/links", response_model=s.CaseRead)
def remove_link(
    case_id: UUID, body: s.LinkRequest, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CaseRead:
    service.remove_link(uow, ctx, case_id, target_case_id=body.target_case_id, link_type=body.link_type)
    uow.session.flush()
    return case_read(uow, ctx, case_id)


@router.post(
    "/projects/{project_id}/test-cases/bulk",
    response_model=s.BulkResponse,
    responses={202: {"model": s.BulkResponse, "description": "Queued (more than 200 cases)"}},
)
def bulk(
    body: s.BulkRequest, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_uow)
) -> Any:
    """US-044 / FR-TD-010: ≤ 200 cases now, more as a job; each case audited with the shared bulk id."""
    ctx.require(service.bulk_permission(body.action))
    if (body.case_ids is None) == (body.filter is None):
        raise ValidationFailed("Send either case_ids or filter")
    case_ids = (
        body.case_ids
        if body.case_ids is not None
        else tq.matching_case_ids(
            uow.session,
            ctx,
            body.filter or {},
            service.BULK_MAX + 1,
            restrict=requirement_restrict(uow, ctx, body.filter or {}),
        )
    )
    if len(case_ids) > service.BULK_MAX:
        raise ValidationFailed(f"At most {service.BULK_MAX} cases per bulk action")
    bulk_id = ids.new_id()
    if len(case_ids) > service.BULK_SYNC_LIMIT:
        job_id = ids.new_id()
        uow.enqueue_job(
            "testcase.bulk",
            {**job_payload(ctx, body.action, case_ids, body.params, bulk_id), "job_id": str(job_id)},
            organization_id=ctx.principal.organization_id,
            dedupe_key=f"bulk:{bulk_id}",
        )
        return JSONResponse(
            s.BulkResponse(bulk_operation_id=bulk_id, job_id=job_id).model_dump(mode="json"), status_code=202
        )
    result = service.apply_bulk(
        uow, ctx, action=body.action, case_ids=case_ids, params=body.params, bulk_id=bulk_id
    )
    return s.BulkResponse(
        bulk_operation_id=bulk_id,
        updated=result.updated,
        skipped=[s.BulkSkipped(**x) for x in result.skipped],
    )


# -- tags -----------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/tags", response_model=list[s.TagRead])
def list_tags(
    ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_read_uow)
) -> list[s.TagRead]:
    """US-045: system tags always exist."""
    ctx.require("project.view")
    return [
        s.TagRead(id=t.id, name=t.name, is_system=t.is_system, usage=n) for t, n in tq.tags(uow.session, ctx)
    ]


@router.post("/projects/{project_id}/tags", response_model=s.TagRead, status_code=status.HTTP_201_CREATED)
def create_tag(
    body: s.TagCreate, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_uow)
) -> s.TagRead:
    t = service.create_tag(uow, ctx, body.name)
    return s.TagRead(id=t.id, name=t.name, is_system=t.is_system, usage=0)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: UUID,
    ctx: AccessContext = Depends(project_context_from("tag", "tag_id")),
    uow: UnitOfWork = Depends(get_uow),
) -> None:
    """Only unused, non-system tags."""
    service.delete_tag(uow, ctx, tag_id)


# -- key resolution (docs/04 §11.1) ---------------------------------------------------------------


@router.get("/projects/{project_id}/resolve", response_model=s.ResolveRead)
def resolve(
    key: str = Query(min_length=1, max_length=40),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> s.ResolveRead:
    """`SPARK-TC-12`, `TC-12`, `12` → case; `SPARK-PL-3` / `PL-3` → plan; `SPARK-CY-1` / `CY-1` → cycle
    (docs/04 §11.1). A bare number is a test case. More entity types arrive with their milestones."""
    from tcms.planning import queries as planning_queries

    ctx.require("project.view")
    upper = key.strip().upper()
    if "-PL-" in upper or upper.startswith("PL-"):
        plan = planning_queries.plan_by_key(uow.session, ctx, key)
        if plan is None:
            raise NotFound()
        return s.ResolveRead(entity_type="test_plan", id=plan.id, key=plan.key)
    if "-CY-" in upper or upper.startswith("CY-"):
        cycle = execution_queries.cycle_by_key(uow.session, ctx, key)
        if cycle is None:
            raise NotFound()
        return s.ResolveRead(entity_type="test_cycle", id=cycle.id, key=cycle.key)
    case = tq.case_by_key(uow.session, ctx, key)
    if case is None:
        raise NotFound()
    return s.ResolveRead(entity_type="test_case", id=case.id, key=case.key)
