"""Background bulk operations on cases (> 200 cases, docs/02 §5.5)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.uow import UnitOfWork
from tcms.platform import notifications
from tcms.platform.jobs.queue import JobInfo, job_handler
from tcms.testdesign import service


def job_payload(
    ctx: AccessContext, action: str, case_ids: list[UUID], params: dict[str, Any], bulk_id: UUID
) -> dict[str, Any]:
    """The actor's context is captured when the job is queued (permissions checked then and again here)."""
    p = ctx.principal
    return {
        "actor": {
            "user_id": str(p.user_id),
            "org_id": str(p.organization_id),
            "is_admin": p.is_org_admin,
            "name": p.display_name,
        },
        "project_id": str(ctx.pid),
        "permissions": sorted(ctx.permissions),
        "request_id": ctx.request_id,
        "action": action,
        "case_ids": [str(c) for c in case_ids],
        "params": params,
        "bulk_id": str(bulk_id),
    }


@job_handler("testcase.bulk")
def run_bulk(job: JobInfo, uow: UnitOfWork) -> None:
    d = job.payload
    a = d["actor"]
    principal = Principal(UUID(a["user_id"]), UUID(a["org_id"]), bool(a["is_admin"]), display_name=a["name"])
    ctx = AccessContext.for_principal(
        principal,
        RequestMeta(d["request_id"]),
        project_id=UUID(d["project_id"]),
        permissions=frozenset(d["permissions"]),
    )
    result = service.apply_bulk(
        uow,
        ctx,
        action=d["action"],
        case_ids=[UUID(c) for c in d["case_ids"]],
        params=d["params"],
        bulk_id=UUID(d["bulk_id"]),
    )
    notifications.notify(
        uow,
        organization_id=principal.organization_id,
        user_ids={principal.user_id} if principal.user_id else set(),
        type="bulk.finished",
        project_id=ctx.pid,
        entity_type=None,
        entity_id=None,
        payload={
            "action": d["action"],
            "updated": result.updated,
            "skipped": len(result.skipped),
            "bulk_id": d["bulk_id"],
        },
    )
