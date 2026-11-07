"""Import use cases: upload, validate (dry run), commit, mapping templates (docs/02 §15; M8 D4, D5).

The upload is read once to list sheets and headers; validation and commit run as jobs that read the
stored file again, so the browser never waits on a large file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.core.enums import TransferStatus
from tcms.core.errors import (
    Conflict,
    FieldError,
    FileTooLarge,
    NotFound,
    UnsupportedFileType,
    ValidationFailed,
)
from tcms.core.uow import UnitOfWork
from tcms.imports import fields as F
from tcms.imports.cases import MAX_ROWS
from tcms.platform import import_mappings, spreadsheets, storage, transfers

MAX_BYTES: Final = 20 * 1024 * 1024
ENTITIES: Final = {"test_case": "testcase.create", "requirement": "requirement.manage"}
SAMPLE_ROWS: Final = 5
MAX_DISTINCT: Final = 30


@dataclass(frozen=True)
class SheetInfo:
    name: str
    columns: list[str]
    rows: int
    sample: list[list[str]]
    suggested: dict[str, str]
    values: dict[str, list[str]]  # column → its distinct values when there are few (enum value mapping)


@dataclass(frozen=True)
class Uploaded:
    transfer: transfers.TransferView
    sheets: list[SheetInfo]


def require(ctx: AccessContext, entity: str) -> None:
    perm = ENTITIES.get(entity)
    if perm is None:
        raise ValidationFailed(
            errors=[FieldError("entity", "invalid_value", "Import test cases or requirements")]
        )
    ctx.require(perm)


def upload(uow: UnitOfWork, ctx: AccessContext, *, entity: str, file_name: str, data: bytes) -> Uploaded:
    """FR-IMP-001 step 1: ≤ 20 MB, CSV or XLSX, ≤ 50,000 rows per sheet."""
    require(ctx, entity)
    if len(data) > MAX_BYTES:
        raise FileTooLarge("The file is larger than 20 MB")
    fmt = (
        "xlsx" if file_name.lower().endswith(".xlsx") else "csv" if file_name.lower().endswith(".csv") else ""
    )
    if not fmt:
        raise UnsupportedFileType("Upload a .csv or .xlsx file")
    try:
        sheets = spreadsheets.read_tables(data, file_name, max_rows=MAX_ROWS)
    except spreadsheets.UnreadableFile as exc:
        raise ValidationFailed(str(exc), errors=[FieldError("file", "unreadable", str(exc))]) from exc
    sheets = [sh for sh in sheets if sh.header]
    if not sheets:
        raise ValidationFailed(errors=[FieldError("file", "empty", "The file has no header row")])
    st = transfers.store()
    key = f"imports/{storage.object_key_for(ctx.principal.organization_id)}.{fmt}"
    st.client.put_object(Bucket=st.bucket, Key=key, Body=data, ContentType=spreadsheets.MEDIA[fmt])
    infos = [
        SheetInfo(
            sh.name,
            sh.header,
            len(sh.data),
            sh.data[:SAMPLE_ROWS],
            F.automap(entity, sh.header),
            _few_values(sh),
        )
        for sh in sheets
    ]
    options = {
        "file_name": file_name[:200],
        "sheets": [{"name": i.name, "columns": i.columns, "rows": i.rows} for i in infos],
    }
    t = transfers.create_import(uow, ctx, entity=entity, format=fmt, source_key=key, options=options)
    return Uploaded(t, infos)


def _few_values(sheet: spreadsheets.Sheet, limit: int = MAX_DISTINCT) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for i, h in enumerate(sheet.header):
        seen: set[str] = set()
        for r in sheet.data:
            v = r[i].strip() if i < len(r) else ""
            if v:
                seen.add(v)
                if len(seen) > limit:
                    break
        if 0 < len(seen) <= limit:
            out[h] = sorted(seen, key=str.lower)
    return out


def _mine(uow: UnitOfWork, ctx: AccessContext, transfer_id: UUID) -> transfers.TransferView:
    t = transfers.get(uow.session, ctx.principal.organization_id, transfer_id)
    if t is None or t.project_id != ctx.pid or t.kind != "import":
        raise NotFound()
    require(ctx, t.entity)
    if t.created_by != ctx.principal.user_id:
        raise NotFound()  # imports are personal work in progress
    return t


def _payload(ctx: AccessContext, transfer_id: UUID) -> dict[str, Any]:
    p = ctx.principal
    return {
        "actor": {
            "user_id": str(p.user_id),
            "org_id": str(p.organization_id),
            "is_admin": p.is_org_admin,
            "name": p.display_name,
            "permissions": sorted(ctx.permissions),
        },
        "request_id": ctx.request_id,
        "project_id": str(ctx.pid),
        "transfer_id": str(transfer_id),
    }


def request_validation(
    uow: UnitOfWork,
    ctx: AccessContext,
    transfer_id: UUID,
    *,
    sheet: str | None,
    mapping: dict[str, str],
    value_maps: dict[str, dict[str, str]],
    options: dict[str, Any],
) -> transfers.TransferView:
    """Step 3: store the mapping and run the dry run in the background."""
    t = _mine(uow, ctx, transfer_id)
    if t.status not in ("uploaded", "validated", "failed"):
        raise Conflict("The import is already running or finished", code="invalid_status")
    sheets = [sh["name"] for sh in t.options.get("sheets", [])]
    chosen = sheet or (sheets[0] if sheets else None)
    if chosen not in sheets:
        raise ValidationFailed(errors=[FieldError("sheet", "invalid_value", "Choose a sheet of the file")])
    allowed = {f.key for f in F.FIELDS[t.entity]} | {F.IGNORE}
    bad = sorted({v for v in mapping.values() if v not in allowed})
    if bad:
        raise ValidationFailed(
            errors=[FieldError("mapping", "invalid_value", f"Unknown fields: {', '.join(bad)}")]
        )
    new_options = {
        **t.options,
        "sheet": chosen,
        "mapping": mapping,
        "value_maps": value_maps,
        "import_options": options,
    }
    view = transfers.update(
        uow, t.id, status=TransferStatus.validating, options=new_options, summary={}, errors=[]
    )
    uow.enqueue_job(
        "import.validate",
        _payload(ctx, t.id),
        organization_id=ctx.principal.organization_id,
        dedupe_key=f"import.validate:{t.id}:{clock.now().timestamp()}",
    )
    return view


def request_commit(uow: UnitOfWork, ctx: AccessContext, transfer_id: UUID) -> transfers.TransferView:
    """Step 4 (AC-IMP-01): only a validated plan without errors, or with "skip rows with errors"."""
    t = _mine(uow, ctx, transfer_id)
    if t.status != "validated":
        raise Conflict("Validate the file first", code="invalid_status")
    if not t.summary.get("committable"):
        raise Conflict("Fix the errors or choose to skip rows with errors", code="import_has_errors")
    view = transfers.update(uow, t.id, status=TransferStatus.committing)
    uow.enqueue_job(
        "import.commit",
        _payload(ctx, t.id),
        organization_id=ctx.principal.organization_id,
        dedupe_key=f"import.commit:{t.id}",
        max_attempts=1,
    )
    return view


# -- mapping templates (US-151): stored by platform.import_mappings ---------------------------------


def save_template(
    uow: UnitOfWork, ctx: AccessContext, *, entity: str, name: str, mapping: dict[str, Any]
) -> import_mappings.TemplateView:
    require(ctx, entity)
    return import_mappings.save(uow, ctx, entity=entity, name=name, mapping=mapping)


def delete_template(uow: UnitOfWork, ctx: AccessContext, template_id: UUID) -> None:
    t = import_mappings.get(uow, ctx, template_id)
    if t is None:
        raise NotFound()
    require(ctx, t.entity)
    import_mappings.delete(uow, ctx, template_id)
