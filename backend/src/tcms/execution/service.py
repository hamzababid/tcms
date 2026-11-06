"""Cycle and run use cases (docs/02 §7.1–7.2; docs/04 §5.1–5.2, §5.7).

The only write entry points of the execution module. Every write checks permission, validates via
rules.py, writes, and audits in one transaction (CLAUDE.md rule 2). Audit action names follow
docs/02 §13.1 (`cycle.*`, `run.*`, `result.discarded`); run events are one per run and share a
`bulk_operation_id` (docs/04 §5.2). Attempts (start, record, finalize, discard; M4) audit
`result.started/draft_taken_over/finalized/corrected/discarded`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from tcms.core import clock, ids
from tcms.core.concurrency import check_row_version
from tcms.core.context import AccessContext
from tcms.core.enums import CycleStatus, ResultSource, ResultState, ResultStatus, RunStatus, StepStatus
from tcms.core.errors import (
    Conflict,
    FieldError,
    Forbidden,
    ImmutableRecord,
    NotFound,
    PermissionDenied,
    RuleViolation,
    ValidationFailed,
)
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.execution import queries as exec_queries
from tcms.execution import repository as repo
from tcms.execution import rules
from tcms.execution.errors import (
    AlreadyLatest,
    CycleClosed,
    DraftExists,
    DraftsExist,
    InvalidStatus,
    NoEligibleVersion,
    ReasonRequired,
    RunHasResults,
    RunSuperseded,
)
from tcms.execution.models import TestCycle, TestResult, TestRun, TestStepResult
from tcms.identity import queries as identity_queries
from tcms.planning import queries as planning_queries
from tcms.platform import attachments, notifications
from tcms.platform.records import RecordRef
from tcms.testdesign import queries as testdesign_queries
from tcms.testdesign.queries import CaseRef
from tcms.workspace import queries as workspace_queries
from tcms.workspace import service as workspace
from tcms.workspace.errors import NameTaken


def _uid(ctx: AccessContext) -> UUID:
    if ctx.principal.user_id is None:
        raise RuntimeError("user principal required")
    return ctx.principal.user_id


def _touch(row: Any, ctx: AccessContext) -> None:
    row.updated_at = clock.now()
    row.updated_by = ctx.principal.user_id
    row.row_version += 1


def _cycle(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, for_update: bool = False) -> TestCycle:
    c = repo.cycle(uow.session, ctx, cycle_id, for_update=for_update)
    if c is None:
        raise NotFound()
    return c


def _run(uow: UnitOfWork, ctx: AccessContext, run_id: UUID, *, for_update: bool = False) -> TestRun:
    r = repo.run(uow.session, ctx, run_id, for_update=for_update)
    if r is None:
        raise NotFound()
    return r


def _open(cycle: TestCycle) -> None:
    """BR-11: a closed cycle accepts no changes to its runs or assignments."""
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()


def _approval_required(uow: UnitOfWork, ctx: AccessContext) -> bool:
    p = workspace_queries.project(uow.session, ctx.principal.organization_id, ctx.pid)
    if p is None:
        raise NotFound()
    return bool(workspace_queries.project_settings(p)["approval_required"])


def _active_environment(uow: UnitOfWork, ctx: AccessContext, environment_id: UUID) -> None:
    """TCMS-025b / AC-WS-03: an archived (or unknown) environment cannot be chosen for a new cycle."""
    active = {
        e.id
        for e in workspace_queries.environments(
            uow.session, ctx.principal.organization_id, ctx.pid, include_archived=False
        )
    }
    if environment_id not in active:
        raise ValidationFailed(
            "Environment is not available for a new cycle",
            errors=[FieldError("environment_id", "archived_or_unknown", "Choose an active environment")],
        )


def _md(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.replace("\r\n", "\n").strip()
    return v or None


def _run_target(run_: TestRun, cycle: TestCycle, case_key: str) -> AuditTarget:
    """Runs have no key; they are shown as `<cycle key> / <case key>` (docs/02 §2.1)."""
    return AuditTarget("test_run", run_.id, f"{cycle.key} / {case_key}")


def _case_keys(uow: UnitOfWork, ctx: AccessContext, runs: list[TestRun]) -> dict[UUID, str]:
    refs = testdesign_queries.case_refs(uow.session, ctx, [r.test_case_id for r in runs])
    return {cid: ref.key for cid, ref in refs.items()}


# -- selection (docs/06 §4.6 `selection`, docs/02 §6.3) -------------------------------------------


@dataclass(frozen=True)
class Selection:
    """Which cases a cycle gets.

    `from_plan`: the plan's cases, narrowed by `folder_ids`, `tags` and `priorities` when given
    ("From plan … filter: Priority / Tag / Folder", docs/07 §5.8). Otherwise the union of `case_ids`,
    the cases in `folder_ids` (with subfolders) and the cases tagged with `tags`, narrowed by
    `priorities`.
    """

    from_plan: bool = False
    case_ids: list[UUID] = field(default_factory=list)
    folder_ids: list[UUID] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)


def _dedup(items: list[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    out: list[UUID] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _resolve_case_ids(
    uow: UnitOfWork, ctx: AccessContext, selection: Selection, *, plan_id: UUID | None
) -> list[UUID]:
    s = uow.session
    if selection.from_plan:
        if plan_id is None:
            raise ValidationFailed(
                "Choose a plan to take cases from",
                errors=[FieldError("plan_id", "field_required", "Choose a plan")],
            )
        ids_ = planning_queries.plan_case_ids(s, ctx, plan_id)
        if selection.folder_ids:
            in_folders = set(
                testdesign_queries.case_ids_in_folders(s, ctx, selection.folder_ids, include_subfolders=True)
            )
            ids_ = [c for c in ids_ if c in in_folders]
        if selection.tags:
            tagged = set(testdesign_queries.case_ids_with_tags(s, ctx, selection.tags))
            ids_ = [c for c in ids_ if c in tagged]
    else:
        ids_ = list(selection.case_ids)
        if selection.folder_ids:
            ids_ += testdesign_queries.case_ids_in_folders(
                s, ctx, selection.folder_ids, include_subfolders=True
            )
        if selection.tags:
            ids_ += testdesign_queries.case_ids_with_tags(s, ctx, selection.tags)
    ids_ = _dedup(ids_)
    if selection.priorities:
        wanted = set(selection.priorities)
        refs = testdesign_queries.case_refs(s, ctx, ids_)
        ids_ = [c for c in ids_ if c in refs and refs[c].priority in wanted]
    return ids_


@dataclass(frozen=True)
class PinResult:
    added: int
    skipped: list[tuple[str, str]]  # (case key or id, reason)


def _create_runs(
    uow: UnitOfWork,
    ctx: AccessContext,
    cycle: TestCycle,
    case_ids: list[UUID],
    *,
    approval_required: bool,
    default_assignee: UUID | None,
    purpose: str,
) -> PinResult:
    """docs/04 §5.2: pin the eligible version per case; skip ineligible and duplicate cases with a
    reason; new runs go to the end in folder tree order then key (docs/02 §7.1). One `run.added` audit
    event per run, all sharing a bulk id."""
    s = uow.session
    refs = testdesign_queries.case_refs(s, ctx, case_ids)
    existing = repo.active_case_ids(s, ctx, cycle.id)
    skipped: list[tuple[str, str]] = []
    candidates: list[tuple[CaseRef, UUID]] = []
    for cid in case_ids:
        ref = refs.get(cid)
        if ref is None:
            skipped.append((str(cid), "not_found"))
            continue
        if cid in existing:
            skipped.append((ref.key, "already_in_cycle"))  # BR-12
            continue
        elig = rules.eligible_version(ref, approval_required=approval_required, purpose=purpose)
        if elig.version_id is None:
            skipped.append((ref.key, elig.reason or "no_eligible_version"))
            continue
        candidates.append((ref, elig.version_id))
        existing.add(cid)
    if not candidates:
        return PinResult(0, skipped)
    order = testdesign_queries.folder_order(s, ctx)
    version_of = {ref.id: v for ref, v in candidates}
    ordered = rules.tree_order([ref for ref, _ in candidates], order)
    position = repo.max_position(s, ctx, cycle.id)
    now = clock.now()
    uow.bulk_operation_id = uow.bulk_operation_id or ids.new_id()
    for ref in ordered:
        position += 1
        r = repo.insert_run(
            s,
            ctx,
            run_id=ids.new_id(),
            cycle_id=cycle.id,
            test_case_id=ref.id,
            version_id=version_of[ref.id],
            position=position,
            assignee_id=default_assignee,
            now=now,
            actor=ctx.principal.user_id,
        )
        uow.audit(
            ctx,
            "run.added",
            _run_target(r, cycle, ref.key),
            summary=f"{ctx.principal.display_name} added {ref.key} to {cycle.key}",
        )
    return PinResult(len(ordered), skipped)


# -- create cycle ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleData:
    name: str
    environment_id: UUID
    release_id: UUID | None = None
    plan_id: UUID | None = None
    build: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    description: str | None = None
    selection: Selection = field(default_factory=Selection)
    default_assignee_id: UUID | None = None


@dataclass(frozen=True)
class CreateCycleResult:
    cycle: TestCycle
    added: int
    skipped: list[tuple[str, str]]
    runs_pending: bool


def create_cycle(
    uow: UnitOfWork, ctx: AccessContext, data: CycleData, *, cloned_from: TestCycle | None = None
) -> CreateCycleResult:
    """US-080 / FR-EXE-001/002, BR-03/12/13 (AC-PLN-01, TCMS-052/054, TCMS-025b)."""
    ctx.require("cycle.manage")
    s = uow.session
    name = data.name.strip()
    problem = rules.name_problem(name)
    if problem:
        raise ValidationFailed("Invalid name", errors=[problem])
    date_problem = rules.date_order_problem(data.start_date, data.due_date)
    if date_problem:
        raise ValidationFailed("Invalid dates", errors=[date_problem])
    if repo.cycle_name_taken(s, ctx, name):
        raise NameTaken("A cycle with this name already exists")
    _active_environment(uow, ctx, data.environment_id)
    if data.release_id is not None and (
        workspace_queries.release(s, ctx.principal.organization_id, data.release_id) is None
    ):
        raise ValidationFailed(
            "Unknown release", errors=[FieldError("release_id", "not_found", "Unknown release")]
        )
    if data.plan_id is not None and planning_queries.plan_detail(s, ctx, data.plan_id) is None:
        raise ValidationFailed("Unknown plan", errors=[FieldError("plan_id", "not_found", "Unknown plan")])
    if data.default_assignee_id is not None:
        _check_assignable(uow, ctx, data.default_assignee_id, field_name="default_assignee_id")

    case_ids = _resolve_case_ids(uow, ctx, data.selection, plan_id=data.plan_id)
    background = len(case_ids) > rules.INLINE_RUN_LIMIT
    number, key = workspace.allocate_key(uow, ctx, "test_cycle")
    now = clock.now()
    cycle = TestCycle(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        key_num=number,
        key=key,
        name=name,
        description=_md(data.description),
        release_id=data.release_id,
        plan_id=data.plan_id,
        environment_id=data.environment_id,
        build=(data.build or "").strip() or None,
        status=CycleStatus.planned,
        start_date=data.start_date,
        due_date=data.due_date,
        owner_id=_uid(ctx),
        runs_pending=background,
        created_at=now,
        created_by=ctx.principal.user_id,
        updated_at=now,
        updated_by=ctx.principal.user_id,
    )
    s.add(cycle)
    s.flush()
    uow.audit(
        ctx,
        "cycle.created",
        cycle,
        summary=f"{ctx.principal.display_name} created cycle {key}"
        + (f" (clone of {cloned_from.key})" if cloned_from else ""),
        extra={"cloned_from": str(cloned_from.id)} if cloned_from else None,
    )

    if background:
        uow.enqueue_job(
            "cycle.create_runs",
            cycle_runs_payload(ctx, cycle.id, case_ids, data.default_assignee_id),
            organization_id=ctx.principal.organization_id,
            dedupe_key=f"cycle.create_runs:{cycle.id}",
        )
        return CreateCycleResult(cycle, added=0, skipped=[], runs_pending=True)

    pins = _create_runs(
        uow,
        ctx,
        cycle,
        case_ids,
        approval_required=_approval_required(uow, ctx),
        default_assignee=data.default_assignee_id,
        purpose="new_cycle",
    )
    if data.default_assignee_id is not None and pins.added:
        _notify_assigned(uow, ctx, cycle, data.default_assignee_id, pins.added)
    return CreateCycleResult(cycle, pins.added, pins.skipped, runs_pending=False)


# -- background run creation (job) ----------------------------------------------------------------


def cycle_runs_payload(
    ctx: AccessContext, cycle_id: UUID, case_ids: list[UUID], default_assignee: UUID | None
) -> dict[str, Any]:
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
        "cycle_id": str(cycle_id),
        "case_ids": [str(c) for c in case_ids],
        "default_assignee": str(default_assignee) if default_assignee else None,
    }


def create_cycle_runs(
    uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, case_ids: list[UUID], default_assignee: UUID | None
) -> PinResult:
    """Executed by the `cycle.create_runs` job for cycles over the inline limit (docs/04 §5.2)."""
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    result = _create_runs(
        uow,
        ctx,
        cycle,
        case_ids,
        approval_required=_approval_required(uow, ctx),
        default_assignee=default_assignee,
        purpose="new_cycle",
    )
    cycle.runs_pending = False
    _touch(cycle, ctx)
    if default_assignee is not None and result.added:
        _notify_assigned(uow, ctx, cycle, default_assignee, result.added)
    return result


# -- edit / add / remove --------------------------------------------------------------------------


def update_cycle(
    uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, row_version: int, fields: Mapping[str, Any]
) -> TestCycle:
    """docs/06 §4.6 PATCH: name, description, build, dates, environment (only while no attempts)."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    check_row_version(cycle.row_version, row_version)
    _open(cycle)
    changes: dict[str, list[Any]] = {}
    if fields.get("name") is not None:
        new = str(fields["name"]).strip()
        problem = rules.name_problem(new)
        if problem:
            raise ValidationFailed("Invalid name", errors=[problem])
        if new.lower() != cycle.name.lower() and repo.cycle_name_taken(s, ctx, new, exclude=cycle.id):
            raise NameTaken("A cycle with this name already exists")
        if new != cycle.name:
            changes["name"] = [cycle.name, new]
            cycle.name = new
    if fields.get("environment_id") is not None and fields["environment_id"] != cycle.environment_id:
        if repo.run_any_attempt_in_cycle(s, ctx, cycle.id):
            raise RunHasResults("The environment cannot change once runs have attempts")
        _active_environment(uow, ctx, fields["environment_id"])
        changes["environment_id"] = [str(cycle.environment_id), str(fields["environment_id"])]
        cycle.environment_id = fields["environment_id"]
    if "release_id" in fields and fields["release_id"] != cycle.release_id:
        if fields["release_id"] is not None and (
            workspace_queries.release(s, ctx.principal.organization_id, fields["release_id"]) is None
        ):
            raise ValidationFailed(
                "Unknown release", errors=[FieldError("release_id", "not_found", "Unknown release")]
            )
        changes["release_id"] = [str(cycle.release_id), str(fields["release_id"])]
        cycle.release_id = fields["release_id"]
    for name_ in ("description", "build"):
        if name_ in fields:
            new_val = _md(fields[name_])
            if new_val != getattr(cycle, name_):
                changes[name_] = [getattr(cycle, name_), new_val]
                setattr(cycle, name_, new_val)
    for name_ in ("start_date", "due_date"):
        if name_ in fields and fields[name_] != getattr(cycle, name_):
            changes[name_] = [str(getattr(cycle, name_)), str(fields[name_])]
            setattr(cycle, name_, fields[name_])
    date_problem = rules.date_order_problem(cycle.start_date, cycle.due_date)
    if date_problem:
        raise ValidationFailed("Invalid dates", errors=[date_problem])
    if changes:
        _touch(cycle, ctx)
        uow.audit(ctx, "cycle.updated", cycle, changes=changes)
    return cycle


def add_cases(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, selection: Selection) -> PinResult:
    """US-081 / FR-EXE-003, BR-12/13: not in a closed cycle; duplicates and ineligible cases skipped."""
    ctx.require("cycle.manage")
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    _open(cycle)
    case_ids = _resolve_case_ids(uow, ctx, selection, plan_id=cycle.plan_id)
    return _create_runs(
        uow,
        ctx,
        cycle,
        case_ids,
        approval_required=_approval_required(uow, ctx),
        default_assignee=None,
        purpose="new_cycle",
    )


def remove_runs(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, run_ids: list[UUID]) -> int:
    """US-081 (TCMS-057): only not_run runs without attempts; otherwise 409 run_has_results."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    _open(cycle)
    runs = repo.runs_by_ids(s, ctx, run_ids, for_update=True)
    if len(runs) != len(set(run_ids)) or any(r.cycle_id != cycle.id for r in runs):
        raise NotFound("Some runs are not in this cycle")
    with_attempts = repo.run_ids_with_attempts(s, [r.id for r in runs])
    blocked = [r for r in runs if r.status != RunStatus.not_run or r.id in with_attempts]
    if blocked:
        keys = _case_keys(uow, ctx, blocked)
        raise RunHasResults(
            "Runs with results cannot be removed",
            runs=[{"run_id": str(r.id), "case_key": keys.get(r.test_case_id)} for r in blocked],
        )
    keys = _case_keys(uow, ctx, runs)
    uow.bulk_operation_id = ids.new_id()
    for r in runs:
        uow.audit(
            ctx,
            "run.removed",
            _run_target(r, cycle, keys.get(r.test_case_id, "")),
            summary=f"Removed {keys.get(r.test_case_id, 'a run')} from {cycle.key}",
        )
        s.delete(r)
    return len(runs)


# -- assignment -----------------------------------------------------------------------------------


def _check_assignable(
    uow: UnitOfWork, ctx: AccessContext, user_id: UUID, *, field_name: str = "assignee_id"
) -> None:
    perms = identity_queries.user_project_permissions(
        uow.session, ctx.principal.organization_id, ctx.pid, user_id
    )
    if "run.execute" not in perms:
        raise ValidationFailed(
            "The assignee must be a project member who can execute runs",
            errors=[FieldError(field_name, "not_executor", "Choose a member who can execute runs")],
        )


def _notify_assigned(
    uow: UnitOfWork, ctx: AccessContext, cycle: TestCycle, assignee: UUID, count: int
) -> None:
    """docs/02 §2.7 "Runs assigned to me" (in-app; the daily email digest is M7)."""
    if assignee == ctx.principal.user_id:
        return
    notifications.notify(
        uow,
        organization_id=ctx.principal.organization_id,
        user_ids={assignee},
        type="runs.assigned",
        project_id=ctx.pid,
        entity_type="test_cycle",
        entity_id=cycle.id,
        payload={"cycle_key": cycle.key, "cycle_name": cycle.name, "count": count},
    )


def assign_runs(
    uow: UnitOfWork,
    ctx: AccessContext,
    cycle_id: UUID,
    *,
    run_ids: list[UUID] | None,
    filter_: Mapping[str, str] | None,
    assignee_id: UUID | None,
) -> int:
    """US-082 / FR-EXE-004 (TCMS-055): assign or unassign selected runs or every run matching a
    runs-list filter (e.g. a folder). The assignee must be a member holding run.execute."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id)
    _open(cycle)
    if (run_ids is None) == (filter_ is None):
        raise ValidationFailed("Send either run_ids or filter")
    if assignee_id is not None:
        _check_assignable(uow, ctx, assignee_id)
    targets = (
        run_ids if run_ids is not None else exec_queries.run_ids_matching(s, ctx, cycle.id, filter_ or {})
    )
    runs = repo.runs_by_ids(s, ctx, targets, for_update=True)
    if any(r.cycle_id != cycle.id for r in runs):
        raise NotFound("Some runs are not in this cycle")
    changing = [r for r in runs if r.superseded_by_run_id is None and r.assignee_id != assignee_id]
    if not changing:
        return 0
    keys = _case_keys(uow, ctx, changing)
    names = identity_queries.user_refs(s, {a for a in (assignee_id, *(r.assignee_id for r in changing)) if a})
    who = names[assignee_id].display_name if assignee_id and assignee_id in names else "the pool"
    uow.bulk_operation_id = ids.new_id()
    for r in changing:
        before = r.assignee_id
        r.assignee_id = assignee_id
        _touch(r, ctx)
        uow.audit(
            ctx,
            "run.assigned",
            _run_target(r, cycle, keys.get(r.test_case_id, "")),
            changes={
                "assignee_id": [str(before) if before else None, str(assignee_id) if assignee_id else None]
            },
            summary=f"{ctx.principal.display_name} assigned {keys.get(r.test_case_id, 'a run')} to {who}",
        )
    if assignee_id is not None:
        _notify_assigned(uow, ctx, cycle, assignee_id, len(changing))
    return len(changing)


def claim_run(uow: UnitOfWork, ctx: AccessContext, run_id: UUID) -> TestRun:
    """US-082 / FR-EXE-004 (TCMS-056): a tester takes an unassigned run (run.execute)."""
    ctx.require("run.execute")
    r = _run(uow, ctx, run_id, for_update=True)
    cycle = _cycle(uow, ctx, r.cycle_id)
    _open(cycle)
    if r.superseded_by_run_id is not None:
        raise RunSuperseded()
    me = _uid(ctx)
    if r.assignee_id == me:
        return r
    if r.assignee_id is not None:
        raise Conflict("This run is already assigned to someone else")
    r.assignee_id = me
    _touch(r, ctx)
    key = _case_keys(uow, ctx, [r]).get(r.test_case_id, "")
    uow.audit(
        ctx,
        "run.assigned",
        _run_target(r, cycle, key),
        changes={"assignee_id": [None, str(me)]},
        summary=f"{ctx.principal.display_name} claimed {key}",
        extra={"claimed": True},
    )
    return r


# -- lifecycle ------------------------------------------------------------------------------------


_PAST = {"start": "started", "close": "closed", "reopen": "reopened"}


def _transition(cycle: TestCycle, action: str) -> None:
    if not rules.can_transition(action, cycle.status):
        raise InvalidStatus(f"A {cycle.status.value} cycle cannot be {_PAST[action]}")
    cycle.status = rules.next_status(action)


def start_cycle(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> TestCycle:
    """US-084 / FR-EXE-012: planned → active (the automatic start on first execution is M4, BR-30)."""
    ctx.require("cycle.manage")
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    _transition(cycle, "start")
    cycle.started_at = clock.now()
    _touch(cycle, ctx)
    uow.audit(ctx, "cycle.started", cycle, changes={"status": ["planned", "active"]})
    return cycle


@dataclass(frozen=True)
class DraftInfo:
    run_id: UUID
    result_id: UUID
    case_key: str
    executed_by: UUID | None


def drafts(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> list[DraftInfo]:
    rows = repo.drafts_in_cycle(uow.session, ctx, cycle_id)
    keys = _case_keys(uow, ctx, [run_ for _, run_ in rows])
    return [
        DraftInfo(run_.id, res.id, keys.get(run_.test_case_id, ""), res.executed_by) for res, run_ in rows
    ]


def close_cycle(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, discard_drafts: bool) -> TestCycle:
    """US-084 / FR-EXE-012, BR-11 (TCMS-058): draft attempts must be finalized or discarded first. With
    `discard_drafts` the drafts are deleted (`result.discarded`) and their runs fall back to their latest
    final status; not-run runs stay not run."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    if cycle.status != CycleStatus.active:
        raise InvalidStatus("Only an active cycle can be closed")
    pending = repo.drafts_in_cycle(s, ctx, cycle.id)
    if pending and not discard_drafts:
        found = drafts(uow, ctx, cycle.id)
        names = identity_queries.user_refs(s, {d.executed_by for d in found if d.executed_by})
        raise DraftsExist(
            f"{len(found)} run(s) have draft attempts",
            drafts=[
                {
                    "run_id": str(d.run_id),
                    "case_key": d.case_key,
                    "executed_by": names[d.executed_by].display_name if d.executed_by in names else None,
                }
                for d in found
            ],
        )
    if pending:
        keys = _case_keys(uow, ctx, [run_ for _, run_ in pending])
        uow.bulk_operation_id = ids.new_id()
        for res, run_ in pending:
            _remove_draft_evidence(uow, ctx, res)
            repo.delete_draft(s, res)
            run_.status = repo.latest_final_status(s, run_)
            _touch(run_, ctx)
            uow.audit(
                ctx,
                "result.discarded",
                AuditTarget("test_result", res.id, f"{cycle.key} / {keys.get(run_.test_case_id, '')}"),
                summary=f"Draft attempt discarded when {cycle.key} was closed",
            )
    cycle.status = CycleStatus.closed
    cycle.closed_at = clock.now()
    cycle.closed_by = ctx.principal.user_id
    _touch(cycle, ctx)
    uow.audit(ctx, "cycle.closed", cycle, changes={"status": ["active", "closed"]})
    return cycle


def reopen_cycle(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, reason: str) -> TestCycle:
    """US-084 / BR-11 (TCMS-059): requires cycle.reopen and a reason."""
    ctx.require("cycle.reopen")
    if not reason or not reason.strip():
        raise ReasonRequired(errors=[FieldError("reason", "field_required", "Give a reason")])
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    _transition(cycle, "reopen")
    cycle.closed_at = None
    cycle.closed_by = None
    _touch(cycle, ctx)
    uow.audit(
        ctx,
        "cycle.reopened",
        cycle,
        changes={"status": ["closed", "active"]},
        extra={"reason": reason.strip()},
    )
    return cycle


def archive_cycle(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> TestCycle:
    """US-084: closed cycles only; hidden from default lists, still in reports."""
    ctx.require("cycle.manage")
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    if cycle.status != CycleStatus.closed:
        raise InvalidStatus("Only a closed cycle can be archived")
    if cycle.archived_at is not None:
        return cycle
    cycle.archived_at = clock.now()
    _touch(cycle, ctx)
    uow.audit(ctx, "cycle.archived", cycle)
    return cycle


def clone_cycle(
    uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, name: str, only_statuses: list[str] | None
) -> CreateCycleResult:
    """US-084 (TCMS-060): a new cycle with the same cases at their *current* eligible versions and no
    results. `only_statuses` ⊆ {failed, blocked, not_run} keeps only those runs (re-test rounds)."""
    ctx.require("cycle.manage")
    if only_statuses:
        problem = rules.clone_statuses_problem(only_statuses)
        if problem:
            raise ValidationFailed("Invalid statuses", errors=[problem])
    src = _cycle(uow, ctx, cycle_id)
    wanted = set(only_statuses or [])
    case_ids = [
        r.test_case_id
        for r in repo.runs_in_cycle(uow.session, ctx, src.id)
        if not wanted or r.status.value in wanted
    ]
    return create_cycle(
        uow,
        ctx,
        CycleData(
            name=name,
            environment_id=src.environment_id,
            release_id=src.release_id,
            plan_id=src.plan_id,
            build=src.build,
            description=src.description,
            selection=Selection(case_ids=case_ids),
        ),
        cloned_from=src,
    )


def sync_from_plan(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> PinResult:
    """US-085 / BR-31 (AC-PLN-02, TCMS-053): add the plan's cases that are not in the cycle yet; never
    remove runs."""
    ctx.require("cycle.manage")
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    _open(cycle)
    if cycle.plan_id is None:
        raise InvalidStatus("This cycle was not created from a plan")
    plan_case_ids = planning_queries.plan_case_ids(uow.session, ctx, cycle.plan_id)
    already = repo.active_case_ids(uow.session, ctx, cycle.id)
    return _create_runs(
        uow,
        ctx,
        cycle,
        [c for c in plan_case_ids if c not in already],
        approval_required=_approval_required(uow, ctx),
        default_assignee=None,
        purpose="new_cycle",
    )


def close_open_cycles(uow: UnitOfWork, ctx: AccessContext) -> int:
    """Project archive "offers to close" open cycles (docs/02 §4.2): planned cycles are started first,
    drafts are discarded."""
    closed = 0
    for c in repo.open_cycles(uow.session, ctx):
        if c.status == CycleStatus.planned:
            start_cycle(uow, ctx, c.id)
        close_cycle(uow, ctx, c.id, discard_drafts=True)
        closed += 1
    return closed


# -- version actions (BR-04, BR-05) ---------------------------------------------------------------


def _eligible_for(
    uow: UnitOfWork, ctx: AccessContext, run_: TestRun, *, approval_required: bool
) -> UUID | None:
    ref = testdesign_queries.case_refs(uow.session, ctx, [run_.test_case_id]).get(run_.test_case_id)
    if ref is None:
        return None
    return rules.eligible_version(ref, approval_required=approval_required, purpose="existing").version_id


def update_run_version(uow: UnitOfWork, ctx: AccessContext, run_id: UUID) -> TestRun:
    """US-086 / BR-04: update-to-latest while the run has no attempts (cycle.manage, or the assignee
    holding run.execute)."""
    s = uow.session
    run_ = _run(uow, ctx, run_id, for_update=True)
    is_assignee = run_.assignee_id is not None and run_.assignee_id == ctx.principal.user_id
    if not (ctx.has("cycle.manage") or (is_assignee and ctx.has("run.execute"))):
        ctx.require("cycle.manage")
    cycle = _cycle(uow, ctx, run_.cycle_id)
    _open(cycle)
    if run_.superseded_by_run_id is not None:
        raise RunSuperseded()
    if repo.run_has_any_attempt(s, run_.id):
        raise RunHasResults("This run has attempts; replace the run instead")
    version_id = _eligible_for(uow, ctx, run_, approval_required=_approval_required(uow, ctx))
    if version_id is None:
        raise NoEligibleVersion()
    if version_id == run_.test_case_version_id:
        raise AlreadyLatest()
    numbers = testdesign_queries.version_numbers(s, [run_.test_case_version_id, version_id])
    before = run_.test_case_version_id
    run_.test_case_version_id = version_id
    _touch(run_, ctx)
    key = _case_keys(uow, ctx, [run_]).get(run_.test_case_id, "")
    uow.audit(
        ctx,
        "run.version_updated",
        _run_target(run_, cycle, key),
        changes={"version": [numbers.get(before), numbers.get(version_id)]},
    )
    return run_


def update_not_run_versions(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> int:
    """US-086 bulk ("Update all not-run runs in this cycle"): runs without attempts move to their eligible
    version; runs without an eligible version are left as they are."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id)
    _open(cycle)
    runs = [r for r in repo.runs_in_cycle(s, ctx, cycle.id, for_update=True) if r.status == RunStatus.not_run]
    with_attempts = repo.run_ids_with_attempts(s, [r.id for r in runs])
    refs = testdesign_queries.case_refs(s, ctx, [r.test_case_id for r in runs])
    approval_required = _approval_required(uow, ctx)
    changed: list[tuple[TestRun, UUID, UUID]] = []
    for r in runs:
        ref = refs.get(r.test_case_id)
        if r.id in with_attempts or ref is None:
            continue
        v = rules.eligible_version(ref, approval_required=approval_required, purpose="existing").version_id
        if v is not None and v != r.test_case_version_id:
            changed.append((r, r.test_case_version_id, v))
    if not changed:
        return 0
    numbers = testdesign_queries.version_numbers(s, [x for _, a, b in changed for x in (a, b)])
    uow.bulk_operation_id = ids.new_id()
    for r, before, after in changed:
        r.test_case_version_id = after
        _touch(r, ctx)
        uow.audit(
            ctx,
            "run.version_updated",
            _run_target(r, cycle, refs[r.test_case_id].key),
            changes={"version": [numbers.get(before), numbers.get(after)]},
        )
    return len(changed)


def replace_run(uow: UnitOfWork, ctx: AccessContext, run_id: UUID) -> TestRun:
    """US-086 / BR-05 (docs/04 §5.7): a run with a finalized attempt is superseded by a new run at the
    latest eligible version (same position and assignee); the old run keeps its results."""
    ctx.require("cycle.manage")
    s = uow.session
    old = _run(uow, ctx, run_id, for_update=True)
    cycle = _cycle(uow, ctx, old.cycle_id)
    _open(cycle)
    if old.superseded_by_run_id is not None:
        raise RunSuperseded()
    if not repo.run_has_final_attempt(s, old.id):
        raise RunHasResults("Only runs with a finalized result can be replaced; update the version instead")
    version_id = _eligible_for(uow, ctx, old, approval_required=_approval_required(uow, ctx))
    if version_id is None:
        raise NoEligibleVersion()
    if version_id == old.test_case_version_id:
        raise AlreadyLatest("The run already uses the latest eligible version; retest it instead")
    now = clock.now()
    new_id = ids.new_id()
    # Mark the old run first: the partial unique index (BR-12) covers active runs only, and the FK to
    # the new run is DEFERRABLE INITIALLY DEFERRED (docs/04 §5.7).
    old.superseded_by_run_id = new_id
    old.superseded_at = now
    _touch(old, ctx)
    s.flush()
    new = repo.insert_run(
        s,
        ctx,
        run_id=new_id,
        cycle_id=cycle.id,
        test_case_id=old.test_case_id,
        version_id=version_id,
        position=old.position,
        assignee_id=old.assignee_id,
        now=now,
        actor=ctx.principal.user_id,
    )
    s.flush()
    numbers = testdesign_queries.version_numbers(s, [old.test_case_version_id, version_id])
    key = _case_keys(uow, ctx, [old]).get(old.test_case_id, "")
    uow.audit(
        ctx,
        "run.replaced",
        _run_target(old, cycle, key),
        changes={"version": [numbers.get(old.test_case_version_id), numbers.get(version_id)]},
        extra={"new_run_id": str(new.id)},
    )
    return new


# -- reorder --------------------------------------------------------------------------------------


def reorder_runs(
    uow: UnitOfWork,
    ctx: AccessContext,
    cycle_id: UUID,
    *,
    run_ids_in_order: list[UUID] | None,
    sort_by: str | None,
) -> int:
    """US-087 / docs/02 §7.1: an explicit order of every active run, or sort by folder (tree order, then
    key) or priority. Persists `position`; audited as `cycle.updated`."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id)
    _open(cycle)
    runs = repo.runs_in_cycle(s, ctx, cycle.id, for_update=True)
    by_id = {r.id: r for r in runs}
    if (run_ids_in_order is None) == (sort_by is None):
        raise ValidationFailed("Send either run_ids_in_order or sort_by")
    if run_ids_in_order is not None:
        if len(run_ids_in_order) != len(by_id) or set(run_ids_in_order) != set(by_id):
            raise ValidationFailed(
                "List every active run of the cycle exactly once",
                errors=[FieldError("run_ids_in_order", "incomplete", "List every active run once")],
            )
        order = run_ids_in_order
    else:
        refs = testdesign_queries.case_refs(s, ctx, [r.test_case_id for r in runs])
        folders = testdesign_queries.folder_order(s, ctx)
        sorter = rules.priority_order if sort_by == "priority" else rules.tree_order
        case_order = [c.id for c in sorter(list(refs.values()), folders)]
        run_of_case = {r.test_case_id: r.id for r in runs}
        order = [run_of_case[c] for c in case_order if c in run_of_case]
    moved = 0
    for position, rid in enumerate(order, start=1):
        r = by_id[rid]
        if r.position != position:
            r.position = position
            _touch(r, ctx)
            moved += 1
    if moved:
        uow.audit(
            ctx,
            "cycle.updated",
            cycle,
            changes={"run_order": [None, sort_by or "manual"]},
            summary=f"{ctx.principal.display_name} reordered the runs of {cycle.key}",
        )
    return moved


# -- attempts (M4: docs/02 §7.3; docs/04 §5.3–5.5; BR-06…10, BR-30, BR-32) -------------------------


def _result(uow: UnitOfWork, ctx: AccessContext, result_id: UUID, *, for_update: bool = False) -> TestResult:
    res = repo.result(uow.session, ctx, result_id, for_update=for_update)
    if res is None:
        raise NotFound()
    return res


def _result_target(res: TestResult, cycle: TestCycle, case_key: str) -> AuditTarget:
    return AuditTarget("test_result", res.id, f"{cycle.key} / {case_key} #{res.attempt_no}")


def _setting(uow: UnitOfWork, ctx: AccessContext, key: str) -> Any:
    p = workspace_queries.project(uow.session, ctx.principal.organization_id, ctx.pid)
    if p is None:
        raise NotFound()
    return workspace_queries.project_settings(p)[key]


def _require_editor(ctx: AccessContext, res: TestResult) -> None:
    """BR-06: a draft is changed by its executor, or by a user holding cycle.manage."""
    if res.executed_by == ctx.principal.user_id and ctx.has("run.execute"):
        return
    if not ctx.has("cycle.manage"):
        raise PermissionDenied("cycle.manage", "Only the tester running this attempt can change it")


def _require_draft(res: TestResult) -> None:
    if res.state == ResultState.final:
        raise ImmutableRecord("This attempt is finished and can no longer change (BR-06)")


def _activate(uow: UnitOfWork, ctx: AccessContext, cycle: TestCycle) -> None:
    """BR-30: the first execution moves a planned cycle to active."""
    if cycle.status == CycleStatus.planned:
        cycle.status = CycleStatus.active
        cycle.started_at = clock.now()
        _touch(cycle, ctx)
        uow.audit(
            ctx,
            "cycle.started",
            cycle,
            changes={"status": ["planned", "active"]},
            extra={"automatic": True},
            summary=f"{cycle.key} started with its first execution",
        )


@dataclass(frozen=True)
class StartResult:
    result: TestResult
    created: bool


def start_attempt(
    uow: UnitOfWork,
    ctx: AccessContext,
    run_id: UUID,
    *,
    take_over: bool = False,
    corrects_result_id: UUID | None = None,
) -> StartResult:
    """US-090/095/096 (docs/04 §5.3): start, retest or correct; returns the caller's draft if it exists.

    BR-07 one draft per run (409 draft_exists, take-over with cycle.manage), BR-11 closed cycle, BR-30
    auto-start, BR-32 only-assignee setting. Every step of the pinned version starts `not_run`."""
    ctx.require("run.execute")
    s = uow.session
    me = _uid(ctx)
    run_ = _run(uow, ctx, run_id, for_update=True)
    cycle = _cycle(uow, ctx, run_.cycle_id, for_update=True)
    _open(cycle)
    if run_.superseded_by_run_id is not None:
        raise RunSuperseded()
    if not rules.may_execute(
        assignee_id=run_.assignee_id,
        user_id=me,
        only_assignee=bool(_setting(uow, ctx, "only_assignee_executes")),
        has_manage=ctx.has("cycle.manage"),
    ):
        raise Forbidden("Only the assignee may execute this run", code="not_assignee")
    keys = _case_keys(uow, ctx, [run_])
    key = keys.get(run_.test_case_id, "")
    draft = repo.draft_of(s, run_.id)
    if draft is not None:
        if draft.executed_by == me:
            return StartResult(draft, False)
        if take_over and ctx.has("cycle.manage"):
            before = draft.executed_by
            draft.executed_by = me
            draft.updated_at = clock.now()
            draft.updated_by = me
            uow.audit(
                ctx,
                "result.draft_taken_over",
                _result_target(draft, cycle, key),
                changes={"executed_by": [str(before) if before else None, str(me)]},
            )
            return StartResult(draft, False)
        names = identity_queries.user_refs(s, {draft.executed_by} if draft.executed_by else set())
        who = names[draft.executed_by].display_name if draft.executed_by in names else "someone else"
        raise DraftExists(
            f"{who} is running this attempt",
            executed_by=who,
            can_take_over=ctx.has("cycle.manage"),
        )
    if corrects_result_id is not None:
        target = repo.result(s, ctx, corrects_result_id)
        latest = repo.latest_final(s, run_.id)
        if target is None or target.run_id != run_.id or target.state != ResultState.final:
            raise ValidationFailed(
                "Only a finished attempt of this run can be corrected",
                errors=[FieldError("corrects_result_id", "invalid", "Choose a finished attempt of this run")],
            )
        if latest is None or latest.id != target.id:
            raise ValidationFailed(
                "Only the latest result can be corrected",
                errors=[FieldError("corrects_result_id", "not_latest", "Correct the latest result")],
            )
        if target.executed_by != me and not ctx.has("cycle.manage"):
            raise PermissionDenied(
                "cycle.manage", "Only its tester or a user with cycle.manage may correct it"
            )
    version = testdesign_queries.version_view_by_id(s, ctx, run_.test_case_version_id)
    if version is None:  # pragma: no cover - FK guarantees the pinned version
        raise NotFound()
    now = clock.now()
    res = TestResult(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        run_id=run_.id,
        attempt_no=repo.next_attempt_no(s, run_.id),
        state=ResultState.draft,
        source=ResultSource.manual,
        executed_by=me,
        started_at=now,
        build=cycle.build,
        environment_id=cycle.environment_id,
        skipped_steps=0,
        corrects_result_id=corrects_result_id,
        updated_at=now,
        updated_by=me,
    )
    steps = (
        [
            TestStepResult(
                id=ids.new_id(),
                organization_id=res.organization_id,
                project_id=res.project_id,
                result_id=res.id,
                step_id=st.id,
                position=st.position,
                status=StepStatus.not_run,
                updated_at=now,
                updated_by=me,
            )
            for st in version.steps
        ]
        if version.format == "steps"
        else []
    )
    repo.add_result(s, res, steps)
    run_.status = RunStatus.in_progress
    _touch(run_, ctx)
    _activate(uow, ctx, cycle)
    uow.audit(
        ctx,
        "result.started",
        _result_target(res, cycle, key),
        extra={
            "run_id": str(run_.id),
            "version": version.version_no,
            **({"corrects_result_id": str(corrects_result_id)} if corrects_result_id else {}),
        },
        summary=f"{ctx.principal.display_name} started {cycle.key} / {key} (attempt {res.attempt_no})",
    )
    return StartResult(res, True)


def update_attempt(
    uow: UnitOfWork, ctx: AccessContext, result_id: UUID, *, fields: Mapping[str, Any]
) -> TestResult:
    """docs/06 §4.7 PATCH: comment, build, duration_seconds of a draft."""
    res = _result(uow, ctx, result_id, for_update=True)
    _require_draft(res)
    _require_editor(ctx, res)
    if "comment" in fields:
        res.comment = _md(fields["comment"])
    if "build" in fields:
        res.build = (fields["build"] or "").strip() or None
    if "duration_seconds" in fields:
        res.duration_seconds = fields["duration_seconds"]
    res.updated_at = clock.now()
    res.updated_by = ctx.principal.user_id
    return res


def record_step(
    uow: UnitOfWork, ctx: AccessContext, result_id: UUID, step_id: UUID, *, fields: Mapping[str, Any]
) -> TestStepResult:
    """US-090 / docs/04 §5.4: one step of a draft, saved as typed (actual result is checked at finish,
    not here, so testers can type). Last write wins per step; no audit per step."""
    s = uow.session
    res = _result(uow, ctx, result_id, for_update=True)
    _require_draft(res)
    _require_editor(ctx, res)
    row = repo.step_result(s, res.id, step_id)
    if row is None:
        raise NotFound()
    if fields.get("status") is not None:
        row.status = StepStatus(fields["status"])
    if "actual_result" in fields:
        row.actual_result = _md(fields["actual_result"])
    if "comment" in fields:
        row.comment = _md(fields["comment"])
    row.updated_at = clock.now()
    row.updated_by = ctx.principal.user_id
    return row


def pass_remaining(uow: UnitOfWork, ctx: AccessContext, result_id: UUID) -> int:
    """ "Pass all remaining" (docs/02 §7.4): every `not_run` step of the draft becomes passed."""
    res = _result(uow, ctx, result_id, for_update=True)
    _require_draft(res)
    _require_editor(ctx, res)
    now = clock.now()
    n = 0
    for row in repo.step_results(uow.session, res.id):
        if row.status == StepStatus.not_run:
            row.status = StepStatus.passed
            row.updated_at = now
            row.updated_by = ctx.principal.user_id
            n += 1
    return n


def _raise_finalize_problems(problems: list[FieldError]) -> None:
    codes = {p.code for p in problems}
    for code, message in (
        ("actual_result_required", "Describe the actual result of every failed step"),
        ("reason_required", "Give a reason for this result"),
        ("field_required", "Describe what failed"),
    ):
        if code in codes:
            raise RuleViolation(message, code=code, errors=[p for p in problems if p.code == code])
    if problems:
        raise ValidationFailed("Invalid finish request", errors=problems)


@dataclass(frozen=True)
class FinalizeResult:
    result: TestResult
    run: TestRun


def finalize_attempt(
    uow: UnitOfWork,
    ctx: AccessContext,
    result_id: UUID,
    *,
    outcome: str | None,
    reason: str | None,
    duration_seconds: int | None,
) -> FinalizeResult:
    """US-091/092/096/098 (docs/04 §5.5): roll-up by BR-09, BR-10 checks (with review K2), then the
    attempt becomes immutable and the run takes its status (BR-08). Exactly one of two concurrent
    finishes succeeds (row lock + state check, TCMS-090)."""
    s = uow.session
    res = _result(uow, ctx, result_id, for_update=True)
    _require_draft(res)
    _require_editor(ctx, res)
    run_ = _run(uow, ctx, res.run_id, for_update=True)
    cycle = _cycle(uow, ctx, run_.cycle_id)
    _open(cycle)
    version = testdesign_queries.version_view_by_id(s, ctx, run_.test_case_version_id)
    fmt = version.format if version else "steps"
    rows = repo.step_results(s, res.id)
    final = rules.compute_final_status(fmt, [r.status.value for r in rows], outcome)
    reason_text = (reason or "").strip() or None
    problems = rules.finalize_problems(
        fmt,
        [rules.StepRecord(r.position, r.status.value, r.actual_result) for r in rows],
        final.status,
        reason_text,
        res.comment,
    )
    if res.corrects_result_id is not None and reason_text is None:
        problems.append(FieldError("reason", "reason_required", "Say why the result is corrected"))
    _raise_finalize_problems(problems)
    now = clock.now()
    res.state = ResultState.final
    res.status = ResultStatus(final.status)
    res.reason = reason_text
    res.finished_at = now
    res.duration_seconds = rules.duration_seconds(res.started_at, now, duration_seconds)
    res.skipped_steps = final.skipped_steps
    res.updated_at = now
    res.updated_by = ctx.principal.user_id
    before = run_.status.value
    run_.status = RunStatus(final.status)
    run_.latest_result_id = res.id
    run_.needs_retest = False
    _touch(run_, ctx)
    s.flush()
    key = _case_keys(uow, ctx, [run_]).get(run_.test_case_id, "")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    action = "result.corrected" if res.corrects_result_id else "result.finalized"
    label = final.status.replace("_", " ")
    uow.audit(
        ctx,
        action,
        _result_target(res, cycle, key),
        changes={"status": [None, final.status], "run_status": [before, final.status]},
        extra={
            "steps": counts,
            "skipped_steps": final.skipped_steps,
            **({"reason": reason_text} if reason_text else {}),
            **({"corrects_result_id": str(res.corrects_result_id)} if res.corrects_result_id else {}),
        },
        summary=f"{ctx.principal.display_name} recorded {cycle.key} / {key} as {label}",
    )
    return FinalizeResult(res, run_)


def _remove_draft_evidence(uow: UnitOfWork, ctx: AccessContext, res: TestResult) -> None:
    """Attachments uploaded to a discarded draft go with it (docs/02 §7.3 step 5)."""
    step_ids = [r.id for r in repo.step_results(uow.session, res.id)]
    attachments.remove_links_of(uow, ctx.principal.organization_id, "test_step_result", step_ids)


def discard_attempt(uow: UnitOfWork, ctx: AccessContext, result_id: UUID) -> TestRun:
    """docs/02 §7.3 step 5: executor or cycle.manage deletes a draft and its steps and evidence; the run
    falls back to its latest final status (BR-08). Audited with what had been recorded."""
    s = uow.session
    res = _result(uow, ctx, result_id, for_update=True)
    _require_draft(res)
    _require_editor(ctx, res)
    run_ = _run(uow, ctx, res.run_id, for_update=True)
    cycle = _cycle(uow, ctx, run_.cycle_id)
    rows = repo.step_results(s, res.id)
    recorded = [r for r in rows if r.status != StepStatus.not_run]
    key = _case_keys(uow, ctx, [run_]).get(run_.test_case_id, "")
    uow.audit(
        ctx,
        "result.discarded",
        _result_target(res, cycle, key),
        extra={"recorded_steps": len(recorded), "steps": len(rows)},
        summary=(
            f"{ctx.principal.display_name} discarded attempt {res.attempt_no} of {cycle.key} / {key} "
            f"({len(recorded)} of {len(rows)} steps recorded)"
        ),
    )
    _remove_draft_evidence(uow, ctx, res)
    repo.delete_draft(s, res)
    run_.status = repo.latest_final_status(s, run_)
    _touch(run_, ctx)
    return run_


def step_result_record(uow: UnitOfWork, ctx: AccessContext, step_result_id: UUID) -> RecordRef:
    """Evidence on a step of an attempt (docs/06 §4.12): the draft's executor or cycle.manage may attach;
    a final attempt's evidence cannot change (BR-06/BR-28)."""
    s = uow.session
    row = repo.step_result_by_id(s, ctx, step_result_id)
    res = repo.result(s, ctx, row.result_id) if row else None
    run_ = repo.run(s, ctx, res.run_id) if res else None
    cycle = repo.cycle(s, ctx, run_.cycle_id) if run_ else None
    if row is None or res is None or run_ is None or cycle is None:
        raise NotFound()
    final = res.state == ResultState.final
    if not final:
        _require_editor(ctx, res)
    key = _case_keys(uow, ctx, [run_]).get(run_.test_case_id, "")
    return RecordRef(
        "test_step_result",
        row.id,
        ctx.pid,
        f"{cycle.key} / {key} #{res.attempt_no} step {row.position}",
        "run.execute",
        immutable=final,
    )


def verify_run_statuses(uow: UnitOfWork, ctx: AccessContext) -> list[UUID]:
    """docs/04 §5.6: runs whose stored status differs from BR-08 over their attempts. Reports only;
    never fixes (the nightly job logs and alerts)."""
    out: list[UUID] = []
    for run_, results in repo.all_runs_with_attempts(uow.session, ctx):
        expected = rules.derive_run_status(
            [(r.attempt_no, r.state.value, r.status.value if r.status else None) for r in results]
        )
        if run_.status.value != expected:
            out.append(run_.id)
    return out


def projects_with_runs(uow: UnitOfWork) -> list[tuple[UUID, UUID]]:
    """(organization, project) pairs that have runs: the system consistency job visits each tenant."""
    return repo.projects_with_runs(uow.session)
