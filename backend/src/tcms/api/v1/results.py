"""Result attempts and My Work (docs/06 §4.1 `/me/work`, §4.7, §5.5; docs/02 §7.3–7.5)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from tcms.api.deps import Auth, get_read_uow, get_uow, project_context_from
from tcms.api.v1.cycles import result_read, run_read, summary_read
from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.core.enums import ProjectStatus
from tcms.core.uow import UnitOfWork
from tcms.execution import queries as eq
from tcms.execution import schemas as s
from tcms.execution import service
from tcms.identity import queries as identity_queries
from tcms.identity.service import Authenticated
from tcms.reporting import queries as reporting_queries
from tcms.testdesign import queries as tq
from tcms.workspace import queries as workspace_queries

router = APIRouter(prefix="/api/v1", tags=["results"])

RunCtx = Depends(project_context_from("test_run", "run_id"))
ResultCtx = Depends(project_context_from("test_result", "result_id"))


def _result(uow: UnitOfWork, ctx: AccessContext, result_id: UUID) -> s.ResultRead:
    uow.session.flush()
    return result_read(uow, ctx, eq.result_detail(uow.session, ctx, result_id))


@router.post(
    "/runs/{run_id}/results",
    response_model=s.ResultRead,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": s.ResultRead, "description": "The caller's open draft (already started)"}},
)
def start_attempt(
    run_id: UUID,
    body: s.StartAttemptRequest | None = None,
    ctx: AccessContext = RunCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> Any:
    """US-090/095/096 (TCMS-070, 077, 078, 084, 085): start, retest or correct (`corrects_result_id`).
    201 with a new draft, 200 with the caller's existing draft, 409 `draft_exists` for someone else's."""
    req = body or s.StartAttemptRequest()
    started = service.start_attempt(
        uow, ctx, run_id, take_over=req.take_over, corrects_result_id=req.corrects_result_id
    )
    out = _result(uow, ctx, started.result.id)
    return JSONResponse(out.model_dump(mode="json"), status_code=201 if started.created else 200)


@router.get("/results/{result_id}", response_model=s.ResultRead)
def get_result(
    result_id: UUID, ctx: AccessContext = ResultCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> s.ResultRead:
    ctx.require("project.view")
    return result_read(uow, ctx, eq.result_detail(uow.session, ctx, result_id))


@router.patch("/results/{result_id}", response_model=s.ResultRead)
def patch_result(
    result_id: UUID, body: s.AttemptPatch, ctx: AccessContext = ResultCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.ResultRead:
    """Draft comment, build and duration (executor or cycle.manage)."""
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    service.update_attempt(uow, ctx, result_id, fields=fields)
    return _result(uow, ctx, result_id)


@router.patch("/results/{result_id}/steps/{step_id:uuid}", response_model=s.StepResultRead)
def patch_step(
    result_id: UUID,
    step_id: UUID,
    body: s.StepPatch,
    ctx: AccessContext = ResultCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.StepResultRead:
    """US-090 / FR-EXE-006: one step's status, actual result or comment; saved as typed (AC-EXE-09)."""
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    row = service.record_step(uow, ctx, result_id, step_id, fields=fields)
    uow.session.flush()
    return s.StepResultRead(
        id=row.id,
        step_id=row.step_id,
        position=row.position,
        status=row.status.value,
        actual_result=row.actual_result,
        comment=row.comment,
        attachments=next((x.attachments for x in _result(uow, ctx, result_id).steps if x.id == row.id), []),
        updated_at=row.updated_at,
    )


@router.post("/results/{result_id}/steps/bulk", response_model=s.CountResponse)
def pass_remaining(
    result_id: UUID,
    body: s.BulkStepsRequest,
    ctx: AccessContext = ResultCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.CountResponse:
    """ "Pass all remaining" (docs/02 §7.4): `{status: passed, only_not_run: true}`."""
    del body  # the only accepted shape
    return s.CountResponse(count=service.pass_remaining(uow, ctx, result_id))


@router.post("/results/{result_id}/finalize", response_model=s.FinalizeResponse)
def finalize(
    result_id: UUID,
    body: s.FinalizeRequest,
    ctx: AccessContext = ResultCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.FinalizeResponse:
    """US-091/092/096/098 (TCMS-071…075, 079, 080, 089, 090): roll-up (BR-09), reasons (BR-10)."""
    done = service.finalize_attempt(
        uow,
        ctx,
        result_id,
        outcome=body.outcome,
        reason=body.reason,
        duration_seconds=body.duration_seconds,
    )
    result = _result(uow, ctx, done.result.id)
    return s.FinalizeResponse(result=result, run=run_read(uow, ctx, done.run.id, frozenset({"history"})))


@router.delete("/results/{result_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard(result_id: UUID, ctx: AccessContext = ResultCtx, uow: UnitOfWork = Depends(get_uow)) -> None:
    """Discard a draft (executor or cycle.manage); a final attempt answers 409 immutable_record."""
    service.discard_attempt(uow, ctx, result_id)


# -- My Work --------------------------------------------------------------------------------------


@router.get("/me/work", response_model=s.MyWorkRead)
def my_work(auth: Authenticated = Auth, uow: UnitOfWork = Depends(get_read_uow)) -> s.MyWorkRead:
    """US-099 / FR-EXE-014 (docs/07 §5.14): my runs in planned and active cycles of my active projects,
    cases awaiting my review, what I finished today and in the last 7 days, my failed / blocked runs and
    runs to retest, and the bugs I linked (M7 R-142)."""
    se = uow.session
    org = auth.organization_id
    memberships = identity_queries.memberships(se, auth)
    active = {
        p.id: p
        for p in workspace_queries.projects(
            se, org, ids={m.project_id for m in memberships}, status=ProjectStatus.active
        )
    }
    pids = list(active)
    refs = {pid: s.ProjectRef(id=p.id, key=p.key, name=p.name) for pid, p in active.items()}
    cycles = [
        s.MyWorkCycle(
            project=refs[m.cycle.project_id],
            id=m.cycle.id,
            key=m.cycle.key,
            name=m.cycle.name,
            status=m.cycle.status,
            start_date=m.cycle.start_date,
            due_date=m.cycle.due_date,
            summary=summary_read(m.counts, m.needs_retest),
            next_run_id=m.next_run_id,
        )
        for m in eq.my_cycles(se, org, pids, auth.user_id)
        if m.cycle.project_id in refs
    ]
    approvers = [
        m.project_id for m in memberships if m.project_id in active and "testcase.approve" in m.permissions
    ]
    reviews = [
        s.MyWorkReview(project=refs[r.project_id], id=r.id, key=r.key, title=r.title, updated_at=r.updated_at)
        for r in tq.awaiting_review(se, org, auth.user_id, approvers)
    ]
    now = clock.now()
    week = eq.my_week(se, org, pids, auth.user_id, now - timedelta(days=7))
    _, day_start, _ = reporting_queries.today_window()
    today = eq.my_week(se, org, pids, auth.user_id, day_start)
    attention = [
        s.MyWorkAttention(
            project=refs[a.project_id],
            run_id=a.run_id,
            cycle_id=a.cycle_id,
            cycle_key=a.cycle_key,
            case_key=a.case_key,
            title=a.title,
            status=a.status,
            needs_retest=a.needs_retest,
        )
        for a in reporting_queries.my_attention(se, org, pids, auth.user_id)
    ]
    return s.MyWorkRead(
        cycles=cycles,
        reviews=reviews,
        week=summary_read(week),
        today=summary_read(today),
        attention=attention,
        bugs_linked_week=reporting_queries.my_bug_links(se, org, pids, auth.user_id, now - timedelta(days=7)),
    )
