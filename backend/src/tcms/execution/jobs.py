"""Background cycle run creation for large cycles (> 500 cases, docs/02 §7.1, docs/04 §5.2)."""

from __future__ import annotations

from uuid import UUID

from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.uow import UnitOfWork
from tcms.execution import service
from tcms.platform import notifications
from tcms.platform.jobs.queue import JobInfo, job_handler


@job_handler("cycle.create_runs")
def run_create_runs(job: JobInfo, uow: UnitOfWork) -> None:
    d = job.payload
    a = d["actor"]
    principal = Principal(UUID(a["user_id"]), UUID(a["org_id"]), bool(a["is_admin"]), display_name=a["name"])
    ctx = AccessContext.for_principal(
        principal,
        RequestMeta(d["request_id"]),
        project_id=UUID(d["project_id"]),
        permissions=frozenset(d["permissions"]),
    )
    cycle_id = UUID(d["cycle_id"])
    service.create_cycle_runs(
        uow,
        ctx,
        cycle_id,
        [UUID(c) for c in d["case_ids"]],
        UUID(d["default_assignee"]) if d["default_assignee"] else None,
    )
    if principal.user_id is not None:
        notifications.notify(
            uow,
            organization_id=principal.organization_id,
            user_ids={principal.user_id},
            type="cycle.runs_created",
            project_id=ctx.pid,
            entity_type="test_cycle",
            entity_id=cycle_id,
            payload={"case_count": len(d["case_ids"])},
        )
