"""Cycle and run use cases (docs/02 §7.1–7.2; docs/04 §5.1–5.2, §5.7).

The only write entry points of the execution module. Every write checks permission, validates via
rules.py, writes, and audits in one transaction (CLAUDE.md rule 2). Cross-module reads go through other
modules' public `queries` only. Recording and finalizing attempts (the runner) is M4 and lives elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from tcms.core import clock, ids
from tcms.core.concurrency import check_row_version
from tcms.core.context import AccessContext
from tcms.core.enums import CycleStatus, RunStatus
from tcms.core.errors import Conflict, FieldError, NotFound, ValidationFailed
from tcms.core.uow import UnitOfWork
from tcms.execution import repository as repo
from tcms.execution import rules
from tcms.execution.errors import (
    AlreadyLatest,
    CycleClosed,
    DraftsExist,
    InvalidStatus,
    NoEligibleVersion,
    ReasonRequired,
    RunHasResults,
    RunSuperseded,
)
from tcms.execution.models import TestCycle, TestRun
from tcms.identity import queries as identity_queries
from tcms.planning import queries as planning_queries
from tcms.platform import notifications
from tcms.testdesign import queries as testdesign_queries
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


# -- selection resolution -------------------------------------------------------------------------


@dataclass(frozen=True)
class Selection:
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
    resolved: list[UUID] = []
    if selection.from_plan:
        if plan_id is None:
            raise ValidationFailed("from_plan requires plan_id")
        resolved.extend(planning_queries.plan_case_ids(s, ctx, plan_id))
    resolved.extend(selection.case_ids)
    if selection.folder_ids:
        resolved.extend(
            testdesign_queries.case_ids_in_folders(s, ctx, selection.folder_ids, include_subfolders=True)
        )
    if selection.tags:
        resolved.extend(testdesign_queries.case_ids_with_tags(s, ctx, selection.tags))
    return _dedup(resolved)


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
    """docs/04 §5.2: pin the eligible version per case; skip archived/deprecated/duplicate with reasons."""
    s = uow.session
    refs = testdesign_queries.case_refs(s, ctx, case_ids)
    existing = repo.active_case_ids(s, ctx, cycle.id)
    position = repo.max_position(s, ctx, cycle.id)
    now = clock.now()
    added = 0
    skipped: list[tuple[str, str]] = []
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
        position += 1
        repo.insert_run(
            s,
            ctx,
            run_id=ids.new_id(),
            cycle_id=cycle.id,
            test_case_id=cid,
            version_id=elig.version_id,
            position=position,
            assignee_id=default_assignee,
            now=now,
            actor=ctx.principal.user_id,
        )
        existing.add(cid)
        added += 1
    if added:
        uow.audit(
            ctx,
            "run.added",
            cycle,
            summary=f"{added} run(s) added to cycle {cycle.key}",
            extra={"added": added},
        )
    return PinResult(added, skipped)


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


def create_cycle(uow: UnitOfWork, ctx: AccessContext, data: CycleData) -> CreateCycleResult:
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
        raise ValidationFailed("Unknown release", errors=[FieldError("release_id", "not_found", "Unknown")])
    if data.plan_id is not None and planning_queries.plan_detail(s, ctx, data.plan_id) is None:
        raise ValidationFailed("Unknown plan", errors=[FieldError("plan_id", "not_found", "Unknown plan")])
    if data.default_assignee_id is not None:
        _check_assignable(uow, ctx, data.default_assignee_id)

    number, key = workspace.allocate_key(uow, ctx, "test_cycle")
    now = clock.now()
    case_ids = _resolve_case_ids(uow, ctx, data.selection, plan_id=data.plan_id)
    background = len(case_ids) > rules.INLINE_RUN_LIMIT

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
        build=(data.build or None),
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
    uow.audit(ctx, "test_cycle.created", cycle, summary=f"{ctx.principal.display_name} created cycle {key}")

    if background:
        uow.enqueue_job(
            "cycle.create_runs",
            cycle_runs_payload(ctx, cycle.id, case_ids, data.default_assignee_id),
            organization_id=ctx.principal.organization_id,
            dedupe_key=f"cycle.create_runs:{cycle.id}",
        )
        return CreateCycleResult(cycle, added=0, skipped=[], runs_pending=True)

    approval_required = _approval_required(uow, ctx)
    pins = _create_runs(
        uow,
        ctx,
        cycle,
        case_ids,
        approval_required=approval_required,
        default_assignee=data.default_assignee_id,
        purpose="new_cycle",
    )
    return CreateCycleResult(cycle, pins.added, pins.skipped, runs_pending=False)


def _md(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.replace("\r\n", "\n").strip()
    return v or None


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
) -> None:
    """Executed by the `cycle.create_runs` job for cycles over the inline limit (docs/04 §5.2)."""
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    approval_required = _approval_required(uow, ctx)
    _create_runs(
        uow,
        ctx,
        cycle,
        case_ids,
        approval_required=approval_required,
        default_assignee=default_assignee,
        purpose="new_cycle",
    )
    cycle.runs_pending = False
    _touch(cycle, ctx)


# -- edit / add / remove --------------------------------------------------------------------------


def update_cycle(
    uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, row_version: int, fields: dict[str, Any]
) -> TestCycle:
    ctx.require("cycle.manage")
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    check_row_version(cycle.row_version, row_version)
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()
    changes: dict[str, list[Any]] = {}
    if "name" in fields and fields["name"] is not None:
        new = fields["name"].strip()
        problem = rules.name_problem(new)
        if problem:
            raise ValidationFailed("Invalid name", errors=[problem])
        if new.lower() != cycle.name.lower() and repo.cycle_name_taken(
            uow.session, ctx, new, exclude=cycle.id
        ):
            raise NameTaken("A cycle with this name already exists")
        if new != cycle.name:
            changes["name"] = [cycle.name, new]
            cycle.name = new
    if "environment_id" in fields and fields["environment_id"] is not None:
        if repo.run_any_attempt_in_cycle(uow.session, ctx, cycle.id):
            raise RunHasResults("Environment cannot change after attempts exist")
        _active_environment(uow, ctx, fields["environment_id"])
        if fields["environment_id"] != cycle.environment_id:
            changes["environment_id"] = [str(cycle.environment_id), str(fields["environment_id"])]
            cycle.environment_id = fields["environment_id"]
    for name in ("description", "build"):
        if name in fields:
            new_val = _md(fields[name])
            if new_val != getattr(cycle, name):
                changes[name] = [getattr(cycle, name), new_val]
                setattr(cycle, name, new_val)
    for name in ("start_date", "due_date"):
        if name in fields and fields[name] != getattr(cycle, name):
            changes[name] = [str(getattr(cycle, name)), str(fields[name])]
            setattr(cycle, name, fields[name])
    date_problem = rules.date_order_problem(cycle.start_date, cycle.due_date)
    if date_problem:
        raise ValidationFailed("Invalid dates", errors=[date_problem])
    if changes:
        _touch(cycle, ctx)
        uow.audit(ctx, "test_cycle.updated", cycle, changes=changes)
    return cycle


def add_cases(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, selection: Selection) -> PinResult:
    """US-081 / FR-EXE-003, BR-12/13."""
    ctx.require("cycle.manage")
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()
    case_ids = _resolve_case_ids(uow, ctx, selection, plan_id=cycle.plan_id)
    approval_required = _approval_required(uow, ctx)
    return _create_runs(
        uow,
        ctx,
        cycle,
        case_ids,
        approval_required=approval_required,
        default_assignee=None,
        purpose="new_cycle",
    )


def remove_runs(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, run_ids: list[UUID]) -> int:
    """US-081: only not_run runs without attempts, else 409 run_has_results."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()
    runs = repo.runs_by_ids(s, ctx, run_ids, for_update=True)
    removed = 0
    for r in runs:
        if r.cycle_id != cycle.id:
            raise NotFound()
        if r.status != RunStatus.not_run or repo.run_has_any_attempt(s, r.id):
            raise RunHasResults()
        s.delete(r)
        removed += 1
    if removed:
        uow.audit(ctx, "run.removed", cycle, summary=f"{removed} run(s) removed from cycle {cycle.key}")
    return removed


# -- assignment -----------------------------------------------------------------------------------


def _check_assignable(uow: UnitOfWork, ctx: AccessContext, user_id: UUID) -> None:
    perms = identity_queries.user_project_permissions(
        uow.session, ctx.principal.organization_id, ctx.pid, user_id
    )
    if "run.execute" not in perms:
        raise ValidationFailed(
            "Assignee must be a project member who can execute runs",
            errors=[FieldError("assignee_id", "not_executor", "Member lacks run.execute")],
        )


def assign_runs(
    uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, run_ids: list[UUID], assignee_id: UUID | None
) -> int:
    """US-082 / FR-EXE-004: bulk assign/unassign (assignee must hold run.execute)."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id)
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()  # BR-11: assignments cannot change in a closed cycle
    if assignee_id is not None:
        _check_assignable(uow, ctx, assignee_id)
    runs = repo.runs_by_ids(s, ctx, run_ids, for_update=True)
    changed = 0
    for r in runs:
        if r.cycle_id != cycle.id:
            raise NotFound()
        if r.superseded_by_run_id is not None:
            continue
        if r.assignee_id != assignee_id:
            r.assignee_id = assignee_id
            _touch(r, ctx)
            changed += 1
    if changed:
        uow.audit(
            ctx, "run.assigned", cycle, summary=f"{changed} run(s) reassigned", extra={"count": changed}
        )
        if assignee_id is not None:
            notifications.notify(
                uow,
                organization_id=ctx.principal.organization_id,
                user_ids={assignee_id},
                type="runs.assigned",
                project_id=ctx.pid,
                entity_type="test_cycle",
                entity_id=cycle.id,
                payload={"cycle_key": cycle.key, "count": changed},
            )
    return changed


def claim_run(uow: UnitOfWork, ctx: AccessContext, run_id: UUID) -> TestRun:
    """US-082 / FR-EXE-004: a tester claims an unassigned run (requires run.execute)."""
    ctx.require("run.execute")
    r = _run(uow, ctx, run_id, for_update=True)
    cycle = _cycle(uow, ctx, r.cycle_id)
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()
    if r.superseded_by_run_id is not None:
        raise RunSuperseded()
    if r.assignee_id is not None and r.assignee_id != _uid(ctx):
        raise Conflict("This run is already assigned", code="conflict")
    r.assignee_id = _uid(ctx)
    _touch(r, ctx)
    uow.audit(ctx, "run.claimed", cycle, summary=f"{ctx.principal.display_name} claimed a run")
    return r


# -- lifecycle ------------------------------------------------------------------------------------


def _transition(uow: UnitOfWork, ctx: AccessContext, cycle: TestCycle, action: str) -> None:
    if not rules.can_transition(action, cycle.status):
        raise InvalidStatus(f"Cannot {action} a {cycle.status.value} cycle")
    cycle.status = rules.next_status(action)


def start_cycle(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> TestCycle:
    """US-084 / FR-EXE-012: planned → active."""
    ctx.require("cycle.manage")
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    _transition(uow, ctx, cycle, "start")
    cycle.started_at = clock.now()
    _touch(cycle, ctx)
    uow.audit(ctx, "test_cycle.started", cycle, summary=f"Cycle {cycle.key} started")
    return cycle


def close_cycle(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, discard_drafts: bool) -> TestCycle:
    """US-084 / FR-EXE-012, BR-11: drafts must be finalized or discarded first (docs/02 §7.1)."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    if cycle.status != CycleStatus.active:
        raise InvalidStatus("Only an active cycle can be closed")
    drafts = repo.draft_runs(s, ctx, cycle.id)
    if drafts and not discard_drafts:
        raise DraftsExist(draft_run_ids=[str(r.id) for r in drafts])
    # Discarding drafts themselves is a runner (M4) concern; here we only gate the close.
    cycle.status = CycleStatus.closed
    cycle.closed_at = clock.now()
    cycle.closed_by = ctx.principal.user_id
    _touch(cycle, ctx)
    uow.audit(ctx, "test_cycle.closed", cycle, summary=f"Cycle {cycle.key} closed")
    return cycle


def reopen_cycle(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, reason: str) -> TestCycle:
    """US-084 / BR-11 (TCMS-059): reopen requires cycle.reopen and a reason."""
    ctx.require("cycle.reopen")
    if not reason or not reason.strip():
        raise ReasonRequired()
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    _transition(uow, ctx, cycle, "reopen")
    cycle.closed_at = None
    cycle.closed_by = None
    _touch(cycle, ctx)
    uow.audit(
        ctx,
        "test_cycle.reopened",
        cycle,
        summary=f"Cycle {cycle.key} reopened",
        extra={"reason": reason.strip()},
    )
    return cycle


def archive_cycle(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> TestCycle:
    """US-084: closed cycles only."""
    ctx.require("cycle.manage")
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    if cycle.status != CycleStatus.closed:
        raise InvalidStatus("Only a closed cycle can be archived")
    if cycle.archived_at is not None:
        return cycle
    cycle.archived_at = clock.now()
    _touch(cycle, ctx)
    uow.audit(ctx, "test_cycle.archived", cycle, summary=f"Cycle {cycle.key} archived")
    return cycle


def clone_cycle(
    uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID, *, name: str, only_statuses: list[str] | None
) -> CreateCycleResult:
    """US-084 (TCMS-060): new cycle, same cases at current eligible versions, no results.

    `only_statuses` ⊆ {failed, blocked, not_run} carries only runs in those statuses from the source
    (for re-test rounds).
    """
    ctx.require("cycle.manage")
    s = uow.session
    src = _cycle(uow, ctx, cycle_id)
    source_runs = repo.runs_in_cycle(s, ctx, src.id)
    wanted = set(only_statuses or [])
    case_ids = [r.test_case_id for r in source_runs if not wanted or r.status.value in wanted]
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
    )


def sync_from_plan(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> PinResult:
    """US-085 / BR-31 (AC-PLN-02, TCMS-053): add plan cases not yet in the cycle; never remove runs."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id, for_update=True)
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()
    if cycle.plan_id is None:
        raise ValidationFailed("This cycle was not created from a plan")
    plan_case_ids = planning_queries.plan_case_ids(s, ctx, cycle.plan_id)
    approval_required = _approval_required(uow, ctx)
    result = _create_runs(
        uow,
        ctx,
        cycle,
        plan_case_ids,
        approval_required=approval_required,
        default_assignee=None,
        purpose="new_cycle",
    )
    if result.added:
        uow.audit(
            ctx, "test_cycle.synced_from_plan", cycle, summary=f"{result.added} run(s) added from the plan"
        )
    return result


# -- version actions (BR-04, BR-05) ---------------------------------------------------------------


def _eligible_for_run(uow: UnitOfWork, ctx: AccessContext, run: TestRun) -> UUID:
    refs = testdesign_queries.case_refs(uow.session, ctx, [run.test_case_id])
    ref = refs.get(run.test_case_id)
    if ref is None:
        raise NotFound()
    approval_required = _approval_required(uow, ctx)
    elig = rules.eligible_version(ref, approval_required=approval_required, purpose="existing")
    if elig.version_id is None:
        raise NoEligibleVersion()
    return elig.version_id


def update_run_version(uow: UnitOfWork, ctx: AccessContext, run_id: UUID) -> TestRun:
    """US-086 / BR-04: update-to-latest, only while the run has no attempts."""
    s = uow.session
    run = _run(uow, ctx, run_id, for_update=True)
    cycle = _cycle(uow, ctx, run.cycle_id)
    # cycle.manage, or the assignee with run.execute (docs/02 §7.2)
    if not (ctx.has("cycle.manage") or (run.assignee_id == ctx.principal.user_id and ctx.has("run.execute"))):
        ctx.require("cycle.manage")
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()
    if run.superseded_by_run_id is not None:
        raise RunSuperseded()
    if repo.run_has_any_attempt(s, run.id):
        raise RunHasResults("Use Replace run; this run has attempts")  # BR-04
    version_id = _eligible_for_run(uow, ctx, run)
    if version_id == run.test_case_version_id:
        raise AlreadyLatest()
    run.test_case_version_id = version_id
    _touch(run, ctx)
    uow.audit(
        ctx, "run.version_updated", cycle, summary=f"A run in {cycle.key} was updated to the latest version"
    )
    return run


def update_not_run_versions(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> int:
    """US-086 bulk: update every not-run run in the cycle to its eligible version."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id)
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()
    updated = 0
    for run in repo.runs_in_cycle(s, ctx, cycle.id):
        if run.status != RunStatus.not_run or repo.run_has_any_attempt(s, run.id):
            continue
        version_id = _eligible_for_run(uow, ctx, run)
        if version_id != run.test_case_version_id:
            run.test_case_version_id = version_id
            _touch(run, ctx)
            updated += 1
    if updated:
        uow.audit(ctx, "run.version_updated", cycle, summary=f"{updated} not-run run(s) updated to latest")
    return updated


def replace_run(uow: UnitOfWork, ctx: AccessContext, run_id: UUID) -> TestRun:
    """US-086 / BR-05 (docs/04 §5.7): supersede a run with results, new run at the latest version."""
    ctx.require("cycle.manage")
    s = uow.session
    old = _run(uow, ctx, run_id, for_update=True)
    cycle = _cycle(uow, ctx, old.cycle_id)
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()
    if old.superseded_by_run_id is not None:
        raise RunSuperseded()
    if not repo.run_has_final_attempt(s, old.id):
        raise RunHasResults("Replace run requires a finalized attempt")  # otherwise use update-to-latest
    version_id = _eligible_for_run(uow, ctx, old)
    now = clock.now()
    new = repo.insert_run(
        s,
        ctx,
        run_id=ids.new_id(),
        cycle_id=cycle.id,
        test_case_id=old.test_case_id,
        version_id=version_id,
        position=old.position,
        assignee_id=old.assignee_id,
        now=now,
        actor=ctx.principal.user_id,
    )
    # Mark the old run superseded first; the partial unique index is on the active set, and the FK is
    # DEFERRABLE INITIALLY DEFERRED, so this is safe in one transaction (docs/04 §5.7).
    old.superseded_by_run_id = new.id
    old.superseded_at = now
    _touch(old, ctx)
    s.flush()
    uow.audit(ctx, "run.replaced", cycle, summary=f"A run in {cycle.key} was replaced at the latest version")
    return new


# -- reorder --------------------------------------------------------------------------------------


def reorder_runs(
    uow: UnitOfWork,
    ctx: AccessContext,
    cycle_id: UUID,
    *,
    ordered_run_ids: list[UUID] | None,
    sort_by: str | None,
) -> int:
    """US-087 / docs/02 §7.1: explicit order or sort by folder/priority; persists `position`."""
    ctx.require("cycle.manage")
    s = uow.session
    cycle = _cycle(uow, ctx, cycle_id)
    if cycle.status == CycleStatus.closed:
        raise CycleClosed()
    runs = repo.runs_in_cycle(s, ctx, cycle.id)
    by_id = {r.id: r for r in runs}
    if ordered_run_ids is not None:
        if set(ordered_run_ids) != set(by_id):
            raise ValidationFailed("ordered_run_ids must list every active run exactly once")
        order = ordered_run_ids
    elif sort_by in ("folder", "priority"):
        refs = testdesign_queries.case_refs(s, ctx, [r.test_case_id for r in runs])

        def key(r: TestRun) -> Any:
            ref = refs.get(r.test_case_id)
            return (str(ref.folder_id) if ref else "", ref.key if ref else "")

        order = [r.id for r in sorted(runs, key=key)]
    else:
        raise ValidationFailed("Provide ordered_run_ids or sort_by (folder|priority)")
    for position, rid in enumerate(order, start=1):
        run = by_id[rid]
        if run.position != position:
            run.position = position
            _touch(run, ctx)
    uow.audit(ctx, "run.reordered", cycle, summary=f"Runs in cycle {cycle.key} reordered")
    return len(order)
