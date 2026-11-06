"""Report export to CSV and XLSX (FR-RPT-005, docs/02 §11.5; M7 D10; TCMS-117, docs/03 A03).

≤ 10,000 rows: the file is returned at once. Above: a `data_transfers` row and an `export.generate` job
(≤ 500,000 rows) write the file to object storage; the initiator is notified (`export.ready`) and the
file is kept 7 days. Cells that a spreadsheet would read as a formula get a leading `'` (OWASP CSV
injection guidance).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID

from openpyxl import Workbook

from tcms.core import clock
from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.uow import UnitOfWork
from tcms.platform import notifications, storage, transfers
from tcms.platform.jobs.queue import JobInfo, job_handler
from tcms.reporting import reports
from tcms.reporting.queries import Scope
from tcms.reporting.reports import Column, Filters

Format = Literal["csv", "xlsx"]
SYNC_MAX = 10_000
ASYNC_MAX = 500_000
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def safe(value: Any) -> Any:
    """AC-RPT-05: neutralise formula injection in text cells; numbers and dates pass through."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def _cell(value: Any, kind: str) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None) if kind == "datetime" else value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return safe(value)


def write_csv(columns: Iterable[Column], rows: Iterable[dict[str, Any]]) -> bytes:
    cols = list(columns)
    buf = io.StringIO()
    buf.write("\ufeff")  # Excel opens UTF-8 CSV correctly with a BOM
    w = csv.writer(buf)
    w.writerow([safe(c.label) for c in cols])
    for row in rows:
        values = []
        for c in cols:
            v = _cell(row.get(c.key), c.kind)
            values.append(v.isoformat(sep=" ", timespec="seconds") + "Z" if isinstance(v, datetime) else v)
        w.writerow(values)
    return buf.getvalue().encode("utf-8")


def write_xlsx(columns: Iterable[Column], rows: Iterable[dict[str, Any]], title: str) -> bytes:
    cols = list(columns)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title=title[:31])
    ws.append([safe(c.label) for c in cols])
    for row in rows:
        ws.append([_cell(row.get(c.key), c.kind) for c in cols])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def render(report: reports.Report, rows: Iterable[dict[str, Any]], fmt: Format) -> bytes:
    return write_csv(report.columns, rows) if fmt == "csv" else write_xlsx(report.columns, rows, report.title)


def file_name(report: reports.Report, fmt: Format, project_key: str) -> str:
    return f"{project_key}-{report.name}-{clock.now().strftime('%Y%m%d-%H%M')}.{fmt}"


# -- filters as JSON (job payload and transfer options) ---------------------------------------------


def filters_to_json(f: Filters) -> dict[str, Any]:
    sc = f.scope

    def v(x: Any) -> Any:
        if isinstance(x, UUID | date):
            return str(x) if isinstance(x, UUID) else x.isoformat()
        return x

    return {
        "release_id": v(sc.release_id),
        "cycle_ids": [str(c) for c in sc.cycle_ids] if sc.cycle_ids is not None else None,
        "environment_id": v(sc.environment_id),
        "module_folder_id": v(sc.module_folder_id),
        "tester_id": v(sc.tester_id),
        "date_from": v(sc.date_from),
        "date_to": v(sc.date_to),
        "tag": sc.tag,
        "status": list(f.status),
        "assignee_id": v(f.assignee_id),
        "case_status": list(f.case_status),
        "case_type": list(f.case_type),
        "priority": list(f.priority),
    }


def filters_from_json(d: dict[str, Any]) -> Filters:
    def u(x: Any) -> UUID | None:
        return UUID(x) if x else None

    def dt(x: Any) -> date | None:
        return date.fromisoformat(x) if x else None

    scope = Scope(
        release_id=u(d.get("release_id")),
        cycle_ids=tuple(UUID(c) for c in d["cycle_ids"]) if d.get("cycle_ids") is not None else None,
        environment_id=u(d.get("environment_id")),
        module_folder_id=u(d.get("module_folder_id")),
        tester_id=u(d.get("tester_id")),
        date_from=dt(d.get("date_from")),
        date_to=dt(d.get("date_to")),
        tag=d.get("tag"),
    )
    return Filters(
        scope=scope,
        status=tuple(d.get("status") or ()),
        assignee_id=u(d.get("assignee_id")),
        case_status=tuple(d.get("case_status") or ()),
        case_type=tuple(d.get("case_type") or ()),
        priority=tuple(d.get("priority") or ()),
    )


def _limited(rows: Iterator[dict[str, Any]], limit: int) -> Iterator[dict[str, Any]]:
    for i, row in enumerate(rows):
        if i >= limit:
            return
        yield row


@job_handler("export.generate")
def generate(job: JobInfo, uow: UnitOfWork) -> None:
    """Large export: write the file, mark the transfer ready, notify the initiator (D10, D12)."""
    d = job.payload
    a = d["actor"]
    principal = Principal(UUID(a["user_id"]), UUID(a["org_id"]), bool(a["is_admin"]), display_name=a["name"])
    ctx = AccessContext.for_principal(
        principal,
        RequestMeta(d["request_id"]),
        project_id=UUID(d["project_id"]),
        permissions=frozenset(a["permissions"]),
    )
    transfer_id = UUID(d["transfer_id"])
    report = reports.REPORTS[d["report"]]
    fmt: Format = d["format"]
    f = filters_from_json(d["filters"])
    rows = list(_limited(reports.iterate(uow.session, ctx, report, f), ASYNC_MAX))
    data = render(report, rows, fmt)
    st = transfers.store()
    key = f"exports/{storage.object_key_for(ctx.principal.organization_id)}.{fmt}"
    st.client.put_object(Bucket=st.bucket, Key=key, Body=data, ContentType=MEDIA[fmt])
    name = file_name(report, fmt, d["project_key"])
    transfers.finish(
        uow, transfer_id, object_key=key, summary={"rows": len(rows), "file_name": name, "bytes": len(data)}
    )
    transfers.audit_export(
        uow, ctx, entity=f"report:{report.name}", rows=len(rows), format=fmt, transfer_id=transfer_id
    )
    notifications.notify(
        uow,
        organization_id=principal.organization_id,
        user_ids={principal.user_id} if principal.user_id else set(),
        type="export.ready",
        project_id=ctx.pid,
        entity_type="data_transfer",
        entity_id=transfer_id,
        payload={"report": report.name, "title": report.title, "rows": len(rows), "format": fmt},
    )
