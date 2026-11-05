"""Test plan use cases (docs/02 §6; docs/04 §3.2). The only write entry points of the module.

Every write checks permission, validates via rules.py, writes, and audits in one transaction
(CLAUDE.md rule 2). Cross-module reads go through other modules' public `queries` only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from tcms.core import clock, ids
from tcms.core.concurrency import check_row_version
from tcms.core.context import AccessContext
from tcms.core.enums import PlanStatus, PlanType
from tcms.core.errors import FieldError, NotFound, ValidationFailed
from tcms.core.uow import UnitOfWork
from tcms.planning import repository as repo
from tcms.planning import rules
from tcms.planning.errors import PlanArchived
from tcms.planning.models import TestPlan
from tcms.requirements import queries as requirement_queries
from tcms.testdesign import queries as testdesign_queries
from tcms.workspace import queries as workspace_queries
from tcms.workspace import service as workspace
from tcms.workspace.errors import NameTaken


def _uid(ctx: AccessContext) -> UUID:
    if ctx.principal.user_id is None:
        raise RuntimeError("user principal required")
    return ctx.principal.user_id


def _dedup(items: list[UUID]) -> list[UUID]:
    """Order-preserving de-duplication."""
    seen: set[UUID] = set()
    out: list[UUID] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _touch(row: Any, ctx: AccessContext) -> None:
    row.updated_at = clock.now()
    row.updated_by = ctx.principal.user_id
    row.row_version += 1


def _plan(uow: UnitOfWork, ctx: AccessContext, plan_id: UUID, *, for_update: bool = False) -> TestPlan:
    p = repo.plan(uow.session, ctx, plan_id, for_update=for_update)
    if p is None:
        raise NotFound()
    return p


def _require_active(plan: TestPlan) -> None:
    if plan.archived_at is not None or plan.status == PlanStatus.archived:
        raise PlanArchived()


# -- validation helpers ---------------------------------------------------------------------------


def _validate_dates(start: date | None, end: date | None) -> None:
    problem = rules.date_order_problem(start, end)
    if problem:
        raise ValidationFailed("Invalid dates", errors=[problem])


def _validate_risks(risks: list[dict[str, Any]]) -> None:
    problem = rules.risks_problem(risks)
    if problem:
        raise ValidationFailed("Invalid risks", errors=[problem])


def _validate_release(uow: UnitOfWork, ctx: AccessContext, release_id: UUID | None) -> None:
    if release_id is None:
        return
    if workspace_queries.release(uow.session, ctx.principal.organization_id, release_id) is None:
        raise ValidationFailed(
            "Unknown release", errors=[FieldError("release_id", "not_found", "Unknown release")]
        )


def _validate_environments(uow: UnitOfWork, ctx: AccessContext, environment_ids: list[UUID]) -> list[UUID]:
    if not environment_ids:
        return []
    known = {
        e.id
        for e in workspace_queries.environments(
            uow.session, ctx.principal.organization_id, ctx.pid, include_archived=True
        )
    }
    unknown = [e for e in environment_ids if e not in known]
    if unknown:
        raise ValidationFailed(
            "Unknown environment",
            errors=[FieldError("environment_ids", "not_found", "Unknown environment")],
        )
    return _dedup(environment_ids)


# -- create / update ------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanData:
    name: str
    type: PlanType
    release_id: UUID | None = None
    objectives: str | None = None
    scope_in: str | None = None
    scope_out: str | None = None
    entry_criteria: str | None = None
    exit_criteria_notes: str | None = None
    acceptance_criteria: str | None = None
    exit_rules: list[dict[str, Any]] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    environment_ids: list[UUID] = field(default_factory=list)
    member_ids: list[UUID] = field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    owner_id: UUID | None = None


def create_plan(uow: UnitOfWork, ctx: AccessContext, data: PlanData) -> TestPlan:
    """US-070 / FR-PLN-001/005 (TCMS-050)."""
    ctx.require("plan.manage")
    s = uow.session
    name = data.name.strip()
    problem = rules.name_problem(name)
    if problem:
        raise ValidationFailed("Invalid name", errors=[problem])
    if repo.name_taken(s, ctx, name):
        raise NameTaken("A plan with this name already exists")
    _validate_dates(data.start_date, data.end_date)
    _validate_risks(data.risks)
    _validate_release(uow, ctx, data.release_id)
    env_ids = _validate_environments(uow, ctx, data.environment_ids)
    number, key = workspace.allocate_key(uow, ctx, "test_plan")
    now = clock.now()
    plan = TestPlan(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        key_num=number,
        key=key,
        name=name,
        type=data.type,
        status=PlanStatus.draft,
        release_id=data.release_id,
        owner_id=data.owner_id or _uid(ctx),
        objectives=rules.normalize_md(data.objectives),
        scope_in=rules.normalize_md(data.scope_in),
        scope_out=rules.normalize_md(data.scope_out),
        entry_criteria=rules.normalize_md(data.entry_criteria),
        exit_criteria_notes=rules.normalize_md(data.exit_criteria_notes),
        acceptance_criteria=rules.normalize_md(data.acceptance_criteria),
        exit_rules=data.exit_rules,
        risks=data.risks,
        member_ids=list(dict.fromkeys(data.member_ids)),
        start_date=data.start_date,
        end_date=data.end_date,
        created_at=now,
        created_by=ctx.principal.user_id,
        updated_at=now,
        updated_by=ctx.principal.user_id,
    )
    s.add(plan)
    s.flush()
    repo.set_environments(s, plan.id, env_ids)
    uow.audit(ctx, "test_plan.created", plan, summary=f"{ctx.principal.display_name} created plan {key}")
    return plan


_MD_FIELDS = (
    "objectives",
    "scope_in",
    "scope_out",
    "entry_criteria",
    "exit_criteria_notes",
    "acceptance_criteria",
)


def update_plan(
    uow: UnitOfWork, ctx: AccessContext, plan_id: UUID, *, row_version: int, fields: dict[str, Any]
) -> TestPlan:
    """US-070 edit. Metadata update; audited."""
    ctx.require("plan.manage")
    s = uow.session
    plan = _plan(uow, ctx, plan_id, for_update=True)
    _require_active(plan)
    check_row_version(plan.row_version, row_version)

    changes: dict[str, list[Any]] = {}
    new_start = fields.get("start_date", plan.start_date)
    new_end = fields.get("end_date", plan.end_date)
    _validate_dates(new_start, new_end)

    if "name" in fields and fields["name"] is not None:
        new = fields["name"].strip()
        problem = rules.name_problem(new)
        if problem:
            raise ValidationFailed("Invalid name", errors=[problem])
        if new.lower() != plan.name.lower() and repo.name_taken(s, ctx, new, exclude=plan.id):
            raise NameTaken("A plan with this name already exists")
        if new != plan.name:
            changes["name"] = [plan.name, new]
            plan.name = new
    if "risks" in fields and fields["risks"] is not None:
        _validate_risks(fields["risks"])
        changes["risks"] = [plan.risks, fields["risks"]]
        plan.risks = fields["risks"]
    if "exit_rules" in fields and fields["exit_rules"] is not None:
        changes["exit_rules"] = [plan.exit_rules, fields["exit_rules"]]
        plan.exit_rules = fields["exit_rules"]
    if "environment_ids" in fields and fields["environment_ids"] is not None:
        env_ids = _validate_environments(uow, ctx, fields["environment_ids"])
        repo.set_environments(s, plan.id, env_ids)
        changes["environment_ids"] = [None, [str(e) for e in env_ids]]
    if "release_id" in fields:
        _validate_release(uow, ctx, fields["release_id"])
        if fields["release_id"] != plan.release_id:
            changes["release_id"] = [str(plan.release_id), str(fields["release_id"])]
            plan.release_id = fields["release_id"]
    for name in ("type", "status", "owner_id", "start_date", "end_date", "member_ids"):
        if name in fields and fields[name] is not None and getattr(plan, name) != fields[name]:
            changes[name] = [str(getattr(plan, name)), str(fields[name])]
            setattr(plan, name, fields[name])
    for name in _MD_FIELDS:
        if name in fields:
            new_md = rules.normalize_md(fields[name])
            if new_md != getattr(plan, name):
                changes[name] = [getattr(plan, name), new_md]
                setattr(plan, name, new_md)
    if changes:
        _touch(plan, ctx)
        uow.audit(ctx, "test_plan.updated", plan, changes=changes)
    return plan


# -- case selection (FR-PLN-002, BR-13) -----------------------------------------------------------


def _resolve_selection(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    case_ids: list[UUID] | None,
    folder_ids: list[UUID] | None,
    include_subfolders: bool,
    tags: list[str] | None,
    saved_view_id: UUID | None,
) -> list[UUID]:
    if saved_view_id is not None:
        raise ValidationFailed("Saved views are not available until M6 (saved_view_id)")
    resolved: list[UUID] = []
    if case_ids:
        resolved.extend(case_ids)
    if folder_ids:
        resolved.extend(
            testdesign_queries.case_ids_in_folders(
                uow.session, ctx, folder_ids, include_subfolders=include_subfolders
            )
        )
    if tags:
        resolved.extend(testdesign_queries.case_ids_with_tags(uow.session, ctx, tags))
    return _dedup(resolved)


@dataclass(frozen=True)
class SelectionResult:
    added: int
    skipped: list[tuple[str, str]]  # (case key or id, reason)


def add_cases(
    uow: UnitOfWork,
    ctx: AccessContext,
    plan_id: UUID,
    *,
    case_ids: list[UUID] | None,
    folder_ids: list[UUID] | None,
    include_subfolders: bool,
    tags: list[str] | None,
    saved_view_id: UUID | None,
) -> SelectionResult:
    """FR-PLN-002 / BR-13 (TCMS-051): snapshot of explicit ids; exclusions reported with reasons."""
    ctx.require("plan.manage")
    s = uow.session
    plan = _plan(uow, ctx, plan_id)
    _require_active(plan)
    candidate_ids = _resolve_selection(
        uow,
        ctx,
        case_ids=case_ids,
        folder_ids=folder_ids,
        include_subfolders=include_subfolders,
        tags=tags,
        saved_view_id=saved_view_id,
    )
    refs = testdesign_queries.case_refs(s, ctx, candidate_ids)
    existing = set(repo.case_ids(s, ctx, plan_id))
    added = 0
    skipped: list[tuple[str, str]] = []
    now = clock.now()
    for cid in candidate_ids:
        ref = refs.get(cid)
        if ref is None:
            skipped.append((str(cid), "not_found"))
            continue
        if ref.status == "archived":  # BR-13
            skipped.append((ref.key, "archived"))
            continue
        if cid in existing:
            skipped.append((ref.key, "already_in_plan"))
            continue
        repo.add_case(s, ctx, plan_id, cid, ctx.principal.user_id, now)
        existing.add(cid)
        added += 1
    if added:
        uow.audit(
            ctx,
            "test_plan.cases_added",
            plan,
            summary=f"{added} case(s) added to plan {plan.key}",
            extra={"added": added},
        )
    return SelectionResult(added, skipped)


def remove_cases(uow: UnitOfWork, ctx: AccessContext, plan_id: UUID, *, case_ids: list[UUID]) -> int:
    """Removing cases from a plan is free and does not affect existing cycles (docs/02 §6.2)."""
    ctx.require("plan.manage")
    plan = _plan(uow, ctx, plan_id)
    _require_active(plan)
    removed = repo.remove_cases(uow.session, plan_id, case_ids)
    if removed:
        uow.audit(
            ctx, "test_plan.cases_removed", plan, summary=f"{removed} case(s) removed from plan {plan.key}"
        )
    return removed


# -- requirement links (FR-PLN-003) ---------------------------------------------------------------


def link_requirements(
    uow: UnitOfWork, ctx: AccessContext, plan_id: UUID, *, requirement_ids: list[UUID]
) -> int:
    ctx.require("plan.manage")
    s = uow.session
    plan = _plan(uow, ctx, plan_id)
    _require_active(plan)
    valid = requirement_queries.existing_ids(s, ctx, requirement_ids)
    unknown = [r for r in requirement_ids if r not in valid]
    if unknown:
        raise ValidationFailed(
            "Unknown requirement",
            errors=[FieldError("requirement_ids", "not_found", "Unknown requirement")],
        )
    existing = set(repo.requirement_ids(s, plan_id))
    now = clock.now()
    added = 0
    for rid in requirement_ids:
        if rid in existing:
            continue
        repo.add_requirement(s, ctx, plan_id, rid, ctx.principal.user_id, now)
        existing.add(rid)
        added += 1
    if added:
        uow.audit(ctx, "test_plan.requirements_linked", plan, summary=f"{added} requirement(s) linked")
    return added


def unlink_requirements(
    uow: UnitOfWork, ctx: AccessContext, plan_id: UUID, *, requirement_ids: list[UUID]
) -> int:
    ctx.require("plan.manage")
    plan = _plan(uow, ctx, plan_id)
    _require_active(plan)
    removed = repo.remove_requirements(uow.session, plan_id, requirement_ids)
    if removed:
        uow.audit(ctx, "test_plan.requirements_unlinked", plan, summary=f"{removed} requirement(s) unlinked")
    return removed


# -- clone / archive ------------------------------------------------------------------------------


def clone_plan(uow: UnitOfWork, ctx: AccessContext, plan_id: UUID, *, name: str | None) -> TestPlan:
    """US-073 / FR-PLN-006: copy everything except cycles; status draft; name "Copy of …"."""
    ctx.require("plan.manage")
    s = uow.session
    src = _plan(uow, ctx, plan_id)
    new_name = (name or f"Copy of {src.name}").strip()
    problem = rules.name_problem(new_name)
    if problem:
        raise ValidationFailed("Invalid name", errors=[problem])
    if repo.name_taken(s, ctx, new_name):
        raise NameTaken("A plan with this name already exists")
    clone = create_plan(
        uow,
        ctx,
        PlanData(
            name=new_name,
            type=src.type,
            release_id=src.release_id,
            objectives=src.objectives,
            scope_in=src.scope_in,
            scope_out=src.scope_out,
            entry_criteria=src.entry_criteria,
            exit_criteria_notes=src.exit_criteria_notes,
            acceptance_criteria=src.acceptance_criteria,
            exit_rules=list(src.exit_rules),
            risks=list(src.risks),
            environment_ids=repo.environment_ids(s, src.id),
            member_ids=list(src.member_ids),
            start_date=src.start_date,
            end_date=src.end_date,
            owner_id=_uid(ctx),
        ),
    )
    now = clock.now()
    for cid in repo.case_ids(s, ctx, src.id):
        repo.add_case(s, ctx, clone.id, cid, ctx.principal.user_id, now)
    for rid in repo.requirement_ids(s, src.id):
        repo.add_requirement(s, ctx, clone.id, rid, ctx.principal.user_id, now)
    return clone


def archive_plan(uow: UnitOfWork, ctx: AccessContext, plan_id: UUID) -> TestPlan:
    ctx.require("plan.manage")
    plan = _plan(uow, ctx, plan_id, for_update=True)
    if plan.archived_at is not None:
        return plan
    plan.archived_at = clock.now()
    plan.status = PlanStatus.archived
    _touch(plan, ctx)
    uow.audit(ctx, "test_plan.archived", plan, summary=f"Plan {plan.key} archived")
    return plan
