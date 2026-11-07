"""Import wizard and exports of cases and requirement references (docs/06 §4.13; docs/02 §15; M8a)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.responses import JSONResponse

from tcms.api.deps import (
    get_read_uow,
    get_uow,
    project_context,
    project_context_allow_archived,
    project_context_from,
)
from tcms.api.v1.reporting import get_transfer
from tcms.api.v1.test_cases import requirement_restrict
from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.core.errors import FieldError, NotFound, ValidationFailed
from tcms.core.uow import UnitOfWork
from tcms.imports import export as case_export
from tcms.imports import fields as F
from tcms.imports import refs as ref_io
from tcms.imports import schemas as s
from tcms.imports import service
from tcms.platform import import_mappings, spreadsheets, transfers
from tcms.platform.attachments import content_disposition
from tcms.reporting import schemas as rs
from tcms.testdesign import queries as td_queries
from tcms.workspace import queries as workspace_queries

router = APIRouter(prefix="/api/v1", tags=["import-export"])

TransferCtx = Depends(project_context_from("data_transfer", "transfer_id"))
TemplateCtx = Depends(project_context_from("import_mapping", "template_id"))
SYNC_ROWS = 10_000


@router.post(
    "/projects/{project_id}/imports", response_model=s.ImportUploaded, status_code=status.HTTP_201_CREATED
)
def upload_import(
    file: UploadFile = File(),
    entity: s.Entity = Form(),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_uow),
) -> s.ImportUploaded:
    """FR-IMP-001/003 step 1: CSV or XLSX ≤ 20 MB; returns sheets, headers, a sample and a suggested
    mapping."""
    data = file.file.read(service.MAX_BYTES + 1)
    up = service.upload(uow, ctx, entity=entity, file_name=file.filename or "import.csv", data=data)
    return s.ImportUploaded(
        transfer_id=up.transfer.id,
        entity=entity,
        file_name=up.transfer.options["file_name"],
        sheets=[
            s.SheetRead(
                name=i.name,
                columns=i.columns,
                rows=i.rows,
                sample=i.sample,
                suggested_mapping=i.suggested,
                values=i.values,
            )
            for i in up.sheets
        ],
        fields=[
            s.FieldInfo(key=f.key, label=f.label, choices=list(f.choices), step=f.step)
            for f in F.FIELDS[entity]
        ],
    )


@router.post(
    "/data-transfers/{transfer_id}/validate",
    response_model=rs.TransferRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def validate_import(
    transfer_id: UUID,
    body: s.ValidateRequest,
    ctx: AccessContext = TransferCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> rs.TransferRead:
    """Step 3 (dry run, background): counts and row errors appear on `GET /data-transfers/{id}`."""
    service.request_validation(
        uow,
        ctx,
        transfer_id,
        sheet=body.sheet,
        mapping=body.mapping,
        value_maps=body.value_maps,
        options=body.options.model_dump(mode="json"),
    )
    uow.session.flush()
    return get_transfer(transfer_id, ctx, uow)


@router.post(
    "/data-transfers/{transfer_id}/commit",
    response_model=rs.TransferRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def commit_import(
    transfer_id: UUID, ctx: AccessContext = TransferCtx, uow: UnitOfWork = Depends(get_uow)
) -> rs.TransferRead:
    """Step 4 (AC-IMP-01/03): one transaction for the whole file, in the background."""
    service.request_commit(uow, ctx, transfer_id)
    uow.session.flush()
    return get_transfer(transfer_id, ctx, uow)


@router.get(
    "/data-transfers/{transfer_id}/errors",
    responses={200: {"content": {"text/csv": {}}, "description": "Row errors of the dry run"}},
    response_class=Response,
)
def import_errors(
    transfer_id: UUID, ctx: AccessContext = TransferCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> Response:
    t = transfers.get(uow.session, ctx.principal.organization_id, transfer_id)
    if t is None or t.project_id != ctx.pid or t.created_by != ctx.principal.user_id:
        raise NotFound()
    rows = [[e.get("row"), e.get("column") or "", e.get("code"), e.get("message")] for e in t.errors]
    data = spreadsheets.write_csv(["Row", "Column", "Code", "Message"], rows)
    name = f"{t.options.get('file_name', 'import')}-errors.csv"
    return Response(
        data,
        media_type=spreadsheets.MEDIA["csv"],
        headers={
            "Content-Disposition": content_disposition("attachment", name),
            "X-Content-Type-Options": "nosniff",
        },
    )


# -- templates --------------------------------------------------------------------------------------


def _tread(t: import_mappings.TemplateView) -> s.TemplateRead:
    return s.TemplateRead(id=t.id, entity=t.entity, name=t.name, mapping=t.mapping, created_at=t.created_at)


@router.get("/projects/{project_id}/import-mappings", response_model=list[s.TemplateRead])
def list_templates(
    entity: s.Entity | None = None,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> list[s.TemplateRead]:
    ctx.require("project.view")
    return [_tread(t) for t in import_mappings.list_for(uow, ctx, entity)]


@router.post(
    "/projects/{project_id}/import-mappings",
    response_model=s.TemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def save_template(
    body: s.TemplateCreate, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_uow)
) -> s.TemplateRead:
    """US-151: saving under an existing name replaces it."""
    return _tread(service.save_template(uow, ctx, entity=body.entity, name=body.name, mapping=body.mapping))


@router.delete("/import-mappings/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: UUID, ctx: AccessContext = TemplateCtx, uow: UnitOfWork = Depends(get_uow)
) -> Response:
    service.delete_template(uow, ctx, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -- exports ----------------------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/exports",
    responses={
        200: {"content": {"text/csv": {}, spreadsheets.MEDIA["xlsx"]: {}}, "description": "The file"},
        202: {"model": rs.ExportAccepted, "description": "Built in the background; notified when ready"},
    },
)
def export_entity(
    body: s.ExportCreate,
    ctx: AccessContext = Depends(project_context_allow_archived),
    uow: UnitOfWork = Depends(get_uow),
) -> Response:
    """FR-IMP-002/003 (AC-IMP-02): cases in the import layout (one row per step, Key column) or requirement
    references with their linked case keys. ≤ 10,000 rows at once, more in the background."""
    ctx.require("data.export")
    project = workspace_queries.project_ref(uow.session, ctx.principal.organization_id, ctx.pid)
    assert project is not None
    if body.entity == "requirement":
        header, rows = (
            ref_io.EXPORT_HEADER,
            ref_io.export_rows(uow, ctx, include_archived=body.include_archived),
        )
    else:
        if body.case_ids is not None:
            ids = list(dict.fromkeys(body.case_ids))
        else:
            params = {k: v for k, v in body.filters.items() if k not in ("page", "page_size", "sort")}
            ids = td_queries.matching_case_ids(
                uow.session, ctx, params, 100_000, restrict=requirement_restrict(uow, ctx, params)
            )
        if not ids:
            raise ValidationFailed(errors=[FieldError("filters", "no_rows", "No cases match")])
        header, rows = case_export.HEADER, case_export.case_rows(uow, ctx, ids, version=body.version)
    if len(rows) > SYNC_ROWS:
        return _export_later(uow, ctx, body, header, rows, project.key)
    data = _render(header, rows, body.format, body.entity)
    what = "test-cases" if body.entity == "test_case" else "requirements"
    name = f"{project.key}-{what}-{clock.now():%Y%m%d-%H%M}.{body.format}"
    transfers.audit_export(uow, ctx, entity=body.entity, rows=len(rows), format=body.format, transfer_id=None)
    return Response(
        data,
        media_type=spreadsheets.MEDIA[body.format],
        headers={
            "Content-Disposition": content_disposition("attachment", name),
            "X-Content-Type-Options": "nosniff",
        },
    )


def _render(header: list[str], rows: list[list[Any]], fmt: str, entity: str) -> bytes:
    if fmt == "csv":
        return spreadsheets.write_csv(header, rows)
    return spreadsheets.write_xlsx(header, rows, "Test cases" if entity == "test_case" else "Requirements")


def _export_later(
    uow: UnitOfWork,
    ctx: AccessContext,
    body: s.ExportCreate,
    header: list[str],
    rows: list[list[Any]],
    key: str,
) -> Response:
    """Large exports: the rows are already read; the file is written and stored now, the user is told by a
    notification (same record and download as report exports, D7)."""
    from tcms.platform import notifications, storage

    t = transfers.create_export(uow, ctx, entity=body.entity, format=body.format, options={"rows": len(rows)})
    data = _render(header, rows, body.format, body.entity)
    st = transfers.store()
    obj = f"exports/{storage.object_key_for(ctx.principal.organization_id)}.{body.format}"
    st.client.put_object(Bucket=st.bucket, Key=obj, Body=data, ContentType=spreadsheets.MEDIA[body.format])
    name = f"{key}-{body.entity}-{clock.now():%Y%m%d-%H%M}.{body.format}"
    transfers.finish(
        uow, t.id, object_key=obj, summary={"rows": len(rows), "file_name": name, "bytes": len(data)}
    )
    transfers.audit_export(uow, ctx, entity=body.entity, rows=len(rows), format=body.format, transfer_id=t.id)
    if ctx.principal.user_id:
        notifications.notify(
            uow,
            organization_id=ctx.principal.organization_id,
            user_ids={ctx.principal.user_id},
            type="export.ready",
            project_id=ctx.pid,
            entity_type="data_transfer",
            entity_id=t.id,
            payload={
                "title": "Test cases" if body.entity == "test_case" else "Requirements",
                "rows": len(rows),
                "format": body.format,
            },
        )
    return JSONResponse(
        rs.ExportAccepted(transfer_id=t.id, rows=len(rows)).model_dump(mode="json"), status_code=202
    )
