"""Import jobs (docs/04 §10.3; M8 D4): `import.validate` (dry run) and `import.commit`.

The commit re-validates against the current data, then writes the whole file inside one savepoint:
any failure rolls back every case, folder and audit record of the file (AC-IMP-03, TCMS-136) and the
transfer is marked failed with the reason.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.enums import TransferStatus
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.identity import queries as identity_queries
from tcms.imports import cases, refs
from tcms.imports.cases import MAX_ERRORS, Options, Problem
from tcms.platform import notifications, spreadsheets, storage, transfers
from tcms.platform.jobs.queue import JobInfo, job_handler

log = structlog.get_logger()


def _ctx(d: dict[str, Any]) -> AccessContext:
    a = d["actor"]
    principal = Principal(UUID(a["user_id"]), UUID(a["org_id"]), bool(a["is_admin"]), display_name=a["name"])
    return AccessContext.for_principal(
        principal,
        RequestMeta(d["request_id"]),
        project_id=UUID(d["project_id"]),
        permissions=frozenset(a["permissions"]),
    )


def _read(t: transfers.TransferView, source_key: str) -> spreadsheets.Sheet:
    st = transfers.store()
    data = st.client.get_object(Bucket=st.bucket, Key=source_key)["Body"].read()
    sheets = spreadsheets.read_tables(data, f"file.{t.format}", max_rows=cases.MAX_ROWS)
    name = t.options.get("sheet")
    for sh in sheets:
        if sh.name == name:
            return sh
    raise spreadsheets.UnreadableFile(f"The sheet {name} is no longer in the file")


def _members(uow: UnitOfWork, ctx: AccessContext) -> dict[str, UUID]:
    return {
        m.user.email.lower(): m.user.id
        for m in identity_queries.project_members(uow.session, ctx.principal.organization_id, ctx.pid)
    }


def _options(t: transfers.TransferView) -> Options:
    o = dict(t.options.get("import_options") or {})
    target = o.get("target_folder_id")
    return Options(
        mode="create_only" if o.get("mode") == "create_only" else "upsert",
        target_folder_id=UUID(target) if target else None,
        steps_layout="single_cell" if o.get("steps_layout") == "single_cell" else "row_per_step",
        skip_error_rows=bool(o.get("skip_error_rows")),
    )


def _permission_problems(ctx: AccessContext, plan: cases.Plan) -> list[Problem]:
    out = []
    if plan.folders_to_create and not ctx.has("folder.manage"):
        names = ", ".join("/".join(p) for p in plan.folders_to_create[:3])
        out.append(
            Problem(1, "folder", "permission_denied", f"Creating folders ({names}) needs folder.manage")
        )
    if any(c.action == "update" for c in plan.cases) and not ctx.has("testcase.edit"):
        out.append(Problem(1, "key", "permission_denied", "Updating existing cases needs testcase.edit"))
    return out


def _plan(uow: UnitOfWork, ctx: AccessContext, t: transfers.TransferView) -> tuple[Any, Options]:
    sheet = _read(t, t.source_object_key or "")
    mapping = dict(t.options.get("mapping") or {})
    opts = _options(t)
    if t.entity == "requirement":
        return refs.build_plan(uow, ctx, sheet.header, sheet.data, mapping), opts
    keys = cases.keys_in(sheet.header, sheet.data, mapping)
    context = cases.load_context(uow, ctx, keys, _members(uow, ctx), opts.target_folder_id)
    plan = cases.build_plan(
        sheet.header, sheet.data, mapping, dict(t.options.get("value_maps") or {}), opts, context
    )
    plan.file_problems += _permission_problems(ctx, plan)
    return (plan, context), opts


def _summary(plan: Any, opts: Options) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    problems = plan.problems
    summary = {
        "counts": plan.counts,
        "errors": len(problems),
        "committable": plan.committable(opts.skip_error_rows),
        "skip_error_rows": opts.skip_error_rows,
    }
    if isinstance(plan, cases.Plan):
        summary["warnings"] = [w.as_json() for c in plan.cases for w in c.warnings][:MAX_ERRORS]
        summary["folders_to_create"] = ["/".join(p) for p in plan.folders_to_create[:200]]
    return summary, [p.as_json() for p in problems[:MAX_ERRORS]]


@job_handler("import.validate")
def validate(job: JobInfo, uow: UnitOfWork) -> None:
    ctx = _ctx(job.payload)
    tid = UUID(job.payload["transfer_id"])
    t = transfers.get(uow.session, ctx.principal.organization_id, tid)
    if t is None or t.status != "validating":
        return
    try:
        built, opts = _plan(uow, ctx, t)
    except spreadsheets.UnreadableFile as exc:
        transfers.update(
            uow,
            tid,
            status=TransferStatus.failed,
            errors=[{"row": 1, "column": None, "code": "unreadable", "message": str(exc)}],
        )
        return
    plan = built[0] if isinstance(built, tuple) else built
    summary, errors = _summary(plan, opts)
    transfers.update(uow, tid, status=TransferStatus.validated, summary=summary, errors=errors)


@job_handler("import.commit")
def commit(job: JobInfo, uow: UnitOfWork) -> None:
    ctx = _ctx(job.payload)
    tid = UUID(job.payload["transfer_id"])
    t = transfers.get(uow.session, ctx.principal.organization_id, tid)
    if t is None or t.status != "committing":
        return
    uow.bulk_operation_id = tid
    try:
        built, opts = _plan(uow, ctx, t)
        plan = built[0] if isinstance(built, tuple) else built
        if not plan.committable(opts.skip_error_rows):
            summary, errors = _summary(plan, opts)
            transfers.update(uow, tid, status=TransferStatus.validated, summary=summary, errors=errors)
            _notify(
                uow,
                ctx,
                t,
                "import.failed",
                {"reason": "The data changed since the dry run; check the errors"},
            )
            return
        with uow.savepoint():
            if isinstance(plan, cases.Plan):
                result = cases.commit(uow, ctx, plan, opts, built[1])
                counts = {
                    "created": result.created,
                    "updated": result.updated,
                    "unchanged": result.unchanged,
                    "skipped": result.skipped,
                    "folders_created": result.folders_created,
                }
                report = result.report
            else:
                out = refs.commit(uow, ctx, plan)
                report = out.pop("report")
                counts = out
    except Exception as exc:  # AC-IMP-03: nothing of the file remains
        log.warning("import.commit_failed", transfer_id=str(tid), error=str(exc))
        message = getattr(exc, "detail", None) or str(exc) or exc.__class__.__name__
        transfers.update(
            uow,
            tid,
            status=TransferStatus.failed,
            finished=True,
            errors=[
                {
                    "row": 1,
                    "column": None,
                    "code": "commit_failed",
                    "message": f"Nothing was imported: {message}",
                }
            ],
        )
        _notify(uow, ctx, t, "import.failed", {"reason": str(message)[:300]})
        return
    data = spreadsheets.write_csv(["Row", "Result", "Key", "Message"], report)
    st = transfers.store()
    key = f"imports/{storage.object_key_for(ctx.principal.organization_id)}-report.csv"
    st.client.put_object(Bucket=st.bucket, Key=key, Body=data, ContentType=spreadsheets.MEDIA["csv"])
    name = t.options.get("file_name", "import")
    summary = {**t.summary, "result": counts, "file_name": f"{name}-report.csv"}
    transfers.update(
        uow, tid, status=TransferStatus.committed, summary=summary, result_key=key, finished=True
    )
    uow.audit(
        ctx,
        "import.committed",
        AuditTarget("data_transfer", tid, f"import:{t.entity}", ctx.project_id),
        summary=f"{ctx.principal.display_name} imported {name}: "
        + ", ".join(f"{v} {k}" for k, v in counts.items() if v),
        extra={"counts": counts, "entity": t.entity},
    )
    _notify(uow, ctx, t, "import.finished", counts)


def _notify(
    uow: UnitOfWork, ctx: AccessContext, t: transfers.TransferView, type_: str, payload: dict[str, Any]
) -> None:
    if ctx.principal.user_id is None:
        return
    notifications.notify(
        uow,
        organization_id=ctx.principal.organization_id,
        user_ids={ctx.principal.user_id},
        type=type_,
        project_id=ctx.pid,
        entity_type="data_transfer",
        entity_id=t.id,
        payload={"file_name": t.options.get("file_name"), "entity": t.entity, **payload},
    )
