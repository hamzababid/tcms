"""Test design use cases (docs/02 §5; docs/04 §3.2, §4). The only write entry points of the module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.exc import DBAPIError

from tcms.core import clock, ids
from tcms.core.concurrency import check_row_version
from tcms.core.context import AccessContext
from tcms.core.enums import (
    ApprovalMode,
    AutomationStatus,
    CaseLinkType,
    CaseStatus,
    CaseType,
    DesignTechnique,
    PriorityLevel,
)
from tcms.core.errors import Conflict, FieldError, NotFound, ValidationFailed
from tcms.core.events import subscribe
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.identity import queries as identity_queries
from tcms.platform import attachments, notifications
from tcms.platform.records import RecordRef
from tcms.testdesign import repository as repo
from tcms.testdesign import rules
from tcms.testdesign.errors import (
    CaseArchived,
    CaseHasRuns,
    FolderCycle,
    FolderNotEmpty,
    FolderTooDeep,
    InvalidStatus,
    SelfApprovalNotAllowed,
)
from tcms.testdesign.models import Folder, Tag, TestCase, TestCaseLink, TestCaseStep, TestCaseVersion
from tcms.workspace import queries as workspace_queries
from tcms.workspace import service as workspace
from tcms.workspace.errors import NameTaken
from tcms.workspace.service import ApprovalSettingChanged, ProjectCreated

# -- settings and helpers -------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectFlags:
    approval_required: bool
    allow_self_approval: bool


def _flags(uow: UnitOfWork, ctx: AccessContext) -> ProjectFlags:
    p = workspace_queries.project(uow.session, ctx.principal.organization_id, ctx.pid)
    if p is None:
        raise NotFound()
    s = workspace_queries.project_settings(p)
    return ProjectFlags(bool(s["approval_required"]), bool(s["allow_self_approval"]))


def _touch(row: Any, ctx: AccessContext) -> None:
    row.updated_at = clock.now()
    row.updated_by = ctx.principal.user_id
    row.row_version += 1


def _uid(ctx: AccessContext) -> UUID:
    if ctx.principal.user_id is None:
        raise RuntimeError("user principal required")
    return ctx.principal.user_id


# -- folders (FR-TD-001, BR-15) -------------------------------------------------------------------


def _clean_folder_name(name: str) -> str:
    name = name.strip()
    problem = rules.folder_name_problem(name)
    if problem:
        raise ValidationFailed("Invalid folder name", errors=[problem])
    return name


def create_folder(
    uow: UnitOfWork, ctx: AccessContext, *, name: str, parent_id: UUID | None, description: str | None
) -> Folder:
    ctx.require("folder.manage")
    s = uow.session
    name = _clean_folder_name(name)
    parent = None
    if parent_id is not None:
        parent = repo.folder(s, ctx, parent_id)
        if parent is None:
            raise NotFound("Parent folder not found")
        if parent.archived_at is not None:
            raise Conflict("The parent folder is archived", code="folder_archived")
        if parent.depth >= rules.MAX_DEPTH:
            raise FolderTooDeep()
    if repo.sibling_named(s, ctx, parent_id, name):
        raise NameTaken("A folder with this name already exists here")
    now = clock.now()
    folder_id = ids.new_id()
    position = max((f.position for f in repo.siblings(s, ctx, parent_id)), default=0) + 1
    f = Folder(
        id=folder_id,
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        parent_id=parent_id,
        name=name,
        description=rules.normalize_md(description),
        position=position,
        path=rules.child_path(parent.path if parent else None, folder_id),
        depth=(parent.depth + 1) if parent else 1,
        created_at=now,
        created_by=ctx.principal.user_id,
        updated_at=now,
        updated_by=ctx.principal.user_id,
    )
    s.add(f)
    s.flush()
    uow.audit(ctx, "folder.created", f, summary=f"{ctx.principal.display_name} created folder {name}")
    return f


def _folder(uow: UnitOfWork, ctx: AccessContext, folder_id: UUID) -> Folder:
    f = repo.folder(uow.session, ctx, folder_id, for_update=True)
    if f is None:
        raise NotFound()
    return f


def update_folder(
    uow: UnitOfWork,
    ctx: AccessContext,
    folder_id: UUID,
    *,
    row_version: int,
    name: str | None,
    description: str | None,
    description_set: bool,
) -> Folder:
    ctx.require("folder.manage")
    f = _folder(uow, ctx, folder_id)
    check_row_version(f.row_version, row_version)
    changes: dict[str, list[Any]] = {}
    if name is not None and name.strip() != f.name:
        new = _clean_folder_name(name)
        if repo.sibling_named(uow.session, ctx, f.parent_id, new, exclude=f.id):
            raise NameTaken("A folder with this name already exists here")
        changes["name"] = [f.name, new]
        f.name = new
    if description_set:
        new_desc = rules.normalize_md(description)
        if new_desc != f.description:
            changes["description"] = [f.description, new_desc]
            f.description = new_desc
    if changes:
        _touch(f, ctx)
        uow.audit(ctx, "folder.updated", f, changes=changes)
    return f


def move_folder(
    uow: UnitOfWork,
    ctx: AccessContext,
    folder_id: UUID,
    *,
    row_version: int,
    parent_id: UUID | None,
    position: int | None,
) -> Folder:
    """AC-TD-01/02: no cycles; the moved subtree keeps depth ≤ 10; path/depth of the subtree rewritten."""
    ctx.require("folder.manage")
    s = uow.session
    f = _folder(uow, ctx, folder_id)
    check_row_version(f.row_version, row_version)
    target = None
    if parent_id is not None:
        target = repo.folder(s, ctx, parent_id)
        if target is None:
            raise NotFound("Target folder not found")
    sub = repo.subtree(s, ctx, f.path, for_update=True)
    problem = rules.move_problem(
        source_path=f.path,
        source_depth=f.depth,
        subtree_max_depth=max(x.depth for x in sub),
        target_path=target.path if target else None,
        target_depth=target.depth if target else 0,
    )
    if problem == "cycle":
        raise FolderCycle()
    if problem == "too_deep":
        raise FolderTooDeep()
    old_parent = f.parent_id
    if parent_id != old_parent and repo.sibling_named(s, ctx, parent_id, f.name, exclude=f.id):
        raise NameTaken("A folder with this name already exists in the target folder")
    if parent_id != old_parent:
        new_path = rules.child_path(target.path if target else None, f.id)
        repo.rewrite_subtree_paths(s, ctx, f.path, new_path, (target.depth + 1 if target else 1) - f.depth)
        s.expire_all()
        f = _folder(uow, ctx, folder_id)
        f.parent_id = parent_id
    # Reorder among the new siblings (drag and drop): insert at `position` (1-based), renumber.
    others = [x for x in repo.siblings(s, ctx, parent_id, for_update=True) if x.id != f.id]
    index = len(others) if position is None else max(0, min(position - 1, len(others)))
    for i, sib in enumerate([*others[:index], f, *others[index:]], start=1):
        sib.position = i
    _touch(f, ctx)
    uow.audit(
        ctx,
        "folder.moved",
        f,
        changes={
            "parent_id": [str(old_parent) if old_parent else None, str(parent_id) if parent_id else None],
            "position": [None, index + 1],
        },
    )
    return f


def set_folder_archived(uow: UnitOfWork, ctx: AccessContext, folder_id: UUID, *, archived: bool) -> Folder:
    """Archive/restore the subtree (docs/02 §5.1); cases inside stay usable unless archived themselves."""
    ctx.require("folder.manage")
    f = _folder(uow, ctx, folder_id)
    now = clock.now()
    for x in repo.subtree(uow.session, ctx, f.path, for_update=True):
        x.archived_at = now if archived else None
        x.archived_by = ctx.principal.user_id if archived else None
    _touch(f, ctx)
    uow.audit(ctx, "folder.archived" if archived else "folder.restored", f)
    return f


def delete_folder(uow: UnitOfWork, ctx: AccessContext, folder_id: UUID) -> None:
    """BR-15 / AC-TD-03: only without cases (including archived) and without subfolders."""
    ctx.require("folder.manage")
    s = uow.session
    f = _folder(uow, ctx, folder_id)
    if repo.folder_has_children(s, ctx, f.id) or repo.folder_has_any_case(s, ctx, f.id):
        raise FolderNotEmpty()
    uow.audit(ctx, "folder.deleted", f)
    s.delete(f)


# -- case content ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseMetadata:
    folder_id: UUID
    type: CaseType = CaseType.functional
    design_technique: DesignTechnique | None = None
    priority: PriorityLevel = PriorityLevel.medium
    tags: list[str] = field(default_factory=list)
    owner_id: UUID | None = None
    reviewer_id: UUID | None = None
    automation_status: AutomationStatus = AutomationStatus.manual
    automation_keys: list[str] = field(default_factory=list)
    estimated_minutes: int | None = None


@dataclass(frozen=True)
class SaveResult:
    case: TestCase
    version_created: bool
    warnings: list[str] = field(default_factory=list)


def _validated_content(content: rules.Content) -> rules.Content:
    c = rules.normalize_content(content)
    problems = rules.content_problems(c)
    if problems:
        raise ValidationFailed("The test case is not valid", errors=problems)
    return c


def _check_people(
    uow: UnitOfWork, ctx: AccessContext, owner_id: UUID | None, reviewer_id: UUID | None
) -> None:
    s, org = uow.session, ctx.principal.organization_id
    if owner_id is not None and identity_queries.member_permissions(s, org, ctx.pid, owner_id) is None:
        raise ValidationFailed(
            errors=[FieldError("owner_id", "not_member", "The owner must be a project member")]
        )
    if reviewer_id is not None:
        perms = identity_queries.member_permissions(s, org, ctx.pid, reviewer_id)
        if perms is None or "testcase.approve" not in perms:
            raise ValidationFailed(
                errors=[
                    FieldError("reviewer_id", "not_approver", "The reviewer must be able to approve cases")
                ]
            )


def _resolve_tags(uow: UnitOfWork, ctx: AccessContext, names: list[str]) -> list[UUID]:
    names = sorted({n.strip().lower() for n in names if n.strip()})
    problems = rules.tag_problems(names)
    if problems:
        raise ValidationFailed("Invalid tags", errors=problems)
    existing = repo.tags_by_name(uow.session, ctx, names)
    now = clock.now()
    out = []
    for n in names:
        t = existing.get(n)
        if t is None:  # free tags are created on first use (FR-TD-008)
            t = Tag(
                id=ids.new_id(),
                organization_id=ctx.principal.organization_id,
                project_id=ctx.pid,
                name=n,
                is_system=False,
                created_at=now,
                created_by=ctx.principal.user_id,
            )
            uow.session.add(t)
            uow.session.flush()
        out.append(t.id)
    return out


def _set_keys(uow: UnitOfWork, ctx: AccessContext, case_id: UUID, keys: list[str]) -> None:
    keys = [k.strip() for k in keys if k.strip()]
    problems = rules.automation_key_problems(keys)
    if problems:
        raise ValidationFailed("Invalid automation keys", errors=problems)
    taken = repo.automation_keys_taken(uow.session, ctx, keys, exclude_case=case_id)
    if taken:
        raise Conflict(f"Automation key already used: {', '.join(taken)}", code="automation_key_taken")
    repo.set_automation_keys(uow.session, ctx, case_id, keys, ctx.principal.user_id, clock.now())


def _insert_version(
    uow: UnitOfWork,
    ctx: AccessContext,
    case: TestCase,
    content: rules.Content,
    *,
    version_no: int,
    change_note: str | None,
    previous_steps: list[TestCaseStep] | None,
) -> TestCaseVersion:
    """docs/04 §4.2: version + steps; step attachments carried to the same position (unless deleted)."""
    now = clock.now()
    v = TestCaseVersion(
        id=ids.new_id(),
        organization_id=case.organization_id,
        project_id=case.project_id,
        test_case_id=case.id,
        version_no=version_no,
        format=content.format,
        title=content.title,
        description=content.description,
        preconditions=content.preconditions,
        test_data=content.test_data,
        expected_result=content.expected_result,
        postconditions=content.postconditions,
        text_body=content.text_body,
        change_note=(change_note or "").strip()[:500] or None,
        content_hash=rules.content_hash(content),
        created_by=_uid(ctx),
        created_at=now,
    )
    uow.session.add(v)
    uow.session.flush()
    new_steps = []
    for i, st in enumerate(content.steps, start=1):
        row = TestCaseStep(
            id=ids.new_id(),
            organization_id=case.organization_id,
            project_id=case.project_id,
            version_id=v.id,
            position=i,
            action=st.action,
            expected_result=st.expected_result,
            data=st.data,
        )
        uow.session.add(row)
        new_steps.append(row)
    uow.session.flush()
    if previous_steps:
        old_by_pos = {s.position: s for s in previous_steps}
        old_atts = attachments.list_for(
            uow, ctx.principal.organization_id, "test_case_step", [s.id for s in previous_steps]
        )
        for new in new_steps:
            old = old_by_pos.get(new.position)
            if old is not None and old_atts.get(old.id):
                attachments.relink(uow, ctx, [a.id for a in old_atts[old.id]], step_record(case, new))
    case.latest_version_id = v.id
    case.latest_version_no = version_no
    case.title = content.title
    case.format = content.format
    return v


def _approve_version(v: TestCaseVersion, case: TestCase, *, by: UUID | None, mode: ApprovalMode) -> None:
    v.approved_at = clock.now()
    v.approved_by = by
    v.approval_mode = mode
    case.approved_version_id = v.id


def create_case(
    uow: UnitOfWork, ctx: AccessContext, *, content: rules.Content, meta: CaseMetadata
) -> SaveResult:
    """US-050/051: key allocated (BR-16), version 1, status per approval setting (docs/02 §5.4)."""
    ctx.require("testcase.create")
    s = uow.session
    c = _validated_content(content)
    folder = repo.folder(s, ctx, meta.folder_id)
    if folder is None:
        raise ValidationFailed(errors=[FieldError("folder_id", "not_found", "Folder not found")])
    if folder.archived_at is not None:
        raise Conflict("The folder is archived", code="folder_archived")
    owner = meta.owner_id or _uid(ctx)
    _check_people(uow, ctx, owner, meta.reviewer_id)
    if meta.estimated_minutes is not None and not 0 <= meta.estimated_minutes <= 1440:
        raise ValidationFailed(errors=[FieldError("estimated_minutes", "out_of_range", "0–1440 minutes")])
    flags = _flags(uow, ctx)
    outcome = rules.status_for_new_case(flags.approval_required)
    number, key = workspace.allocate_key(uow, ctx, "test_case")
    now = clock.now()
    warnings = (
        ["title_exists"] if repo.title_exists_in_folder(s, ctx, folder.id, c.title, exclude=None) else []
    )
    case = TestCase(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        key_num=number,
        key=key,
        folder_id=folder.id,
        title=c.title,
        format=c.format,
        type=meta.type,
        design_technique=meta.design_technique,
        priority=meta.priority,
        status=outcome.status,
        owner_id=owner,
        reviewer_id=meta.reviewer_id,
        automation_status=meta.automation_status,
        estimated_minutes=meta.estimated_minutes,
        latest_version_no=1,
        created_at=now,
        created_by=ctx.principal.user_id,
        updated_at=now,
        updated_by=ctx.principal.user_id,
    )
    s.add(case)
    s.flush()
    v = _insert_version(uow, ctx, case, c, version_no=1, change_note=None, previous_steps=None)
    if outcome.auto_approve:
        _approve_version(v, case, by=None, mode=ApprovalMode.auto)
    repo.set_case_tags(s, case.id, _resolve_tags(uow, ctx, meta.tags))
    _set_keys(uow, ctx, case.id, meta.automation_keys)
    repo.adjust_case_count(s, folder.id, +1)
    s.flush()
    repo.update_search_vector(s, case.id, c.description)
    uow.audit(
        ctx,
        "test_case.created",
        case,
        changes={"title": [None, c.title], "version": [None, 1], "status": [None, case.status.value]},
        summary=f"{ctx.principal.display_name} created {key} {c.title}",
    )
    return SaveResult(case, True, warnings)


def _case(uow: UnitOfWork, ctx: AccessContext, case_id: UUID) -> TestCase:
    case = repo.case_(uow.session, ctx, case_id, for_update=True)
    if case is None:
        raise NotFound()
    return case


def _editable(case: TestCase) -> None:
    if case.status is CaseStatus.archived:
        raise CaseArchived()


def _version_content(uow: UnitOfWork, v: TestCaseVersion) -> rules.Content:
    steps = repo.steps_of(uow.session, [v.id])[v.id]
    return rules.Content(
        format=v.format,
        title=v.title,
        description=v.description,
        preconditions=v.preconditions,
        test_data=v.test_data,
        expected_result=v.expected_result,
        postconditions=v.postconditions,
        text_body=v.text_body,
        steps=tuple(rules.StepContent(st.action, st.expected_result, st.data) for st in steps),
    )


def update_content(
    uow: UnitOfWork,
    ctx: AccessContext,
    case_id: UUID,
    *,
    content: rules.Content,
    change_note: str | None,
    row_version: int,
) -> SaveResult:
    """BR-01/AC-TD-11/13: a new version only when the normalized content differs (docs/04 §3.2)."""
    s = uow.session
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.edit")
    _editable(case)
    check_row_version(case.row_version, row_version)
    c = _validated_content(content)
    latest = repo.version(s, ctx, case.latest_version_id) if case.latest_version_id else None
    assert latest is not None
    if rules.content_hash(c) == latest.content_hash:
        return SaveResult(case, False)
    previous_steps = repo.steps_of(s, [latest.id])[latest.id]
    v = _insert_version(
        uow,
        ctx,
        case,
        c,
        version_no=latest.version_no + 1,
        change_note=change_note,
        previous_steps=previous_steps,
    )
    flags = _flags(uow, ctx)
    outcome = rules.status_after_new_version(case.status, flags.approval_required)
    old_status = case.status
    case.status = outcome.status
    if outcome.auto_approve:
        _approve_version(v, case, by=None, mode=ApprovalMode.auto)
    _touch(case, ctx)
    s.flush()
    repo.update_search_vector(s, case.id, c.description)
    changes: dict[str, list[Any]] = {"version": [latest.version_no, v.version_no]}
    if old_status != case.status:
        changes["status"] = [old_status.value, case.status.value]
    uow.audit(
        ctx,
        "test_case.version_created",
        case,
        changes=changes,
        summary=f"{ctx.principal.display_name} saved {case.key} v{v.version_no}",
    )
    return SaveResult(case, True)


def restore_version(
    uow: UnitOfWork, ctx: AccessContext, case_id: UUID, *, version_no: int, row_version: int
) -> SaveResult:
    """FR-TD-005: version N's content becomes a new version with note "Restored from v N"."""
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.edit")
    source = repo.version_by_no(uow.session, ctx, case.id, version_no)
    if source is None:
        raise NotFound(f"Version {version_no} not found")
    return update_content(
        uow,
        ctx,
        case_id,
        content=_version_content(uow, source),
        change_note=f"Restored from v{version_no}",
        row_version=row_version,
    )


# -- metadata (not versioned, audited; AC-TD-10) --------------------------------------------------

_META_FIELDS = (
    "type",
    "design_technique",
    "priority",
    "owner_id",
    "reviewer_id",
    "automation_status",
    "estimated_minutes",
)


def update_metadata(
    uow: UnitOfWork,
    ctx: AccessContext,
    case_id: UUID,
    *,
    row_version: int | None,
    fields: dict[str, Any],
    bulk: bool = False,
) -> TestCase:
    s = uow.session
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.edit")
    _editable(case)
    if not bulk:
        check_row_version(case.row_version, row_version)
    changes: dict[str, list[Any]] = {}
    if "owner_id" in fields or "reviewer_id" in fields:
        _check_people(uow, ctx, fields.get("owner_id"), fields.get("reviewer_id"))
    if "owner_id" in fields and fields["owner_id"] is None:
        raise ValidationFailed(errors=[FieldError("owner_id", "required", "A case needs an owner")])
    if fields.get("estimated_minutes") is not None and not 0 <= fields["estimated_minutes"] <= 1440:
        raise ValidationFailed(errors=[FieldError("estimated_minutes", "out_of_range", "0–1440 minutes")])
    for name in _META_FIELDS:
        if name in fields and fields[name] != getattr(case, name):
            old = getattr(case, name)
            changes[name] = [_j(old), _j(fields[name])]
            setattr(case, name, fields[name])
    moved = False
    if "folder_id" in fields and fields["folder_id"] != case.folder_id:
        target = repo.folder(s, ctx, fields["folder_id"])
        if target is None:
            raise ValidationFailed(errors=[FieldError("folder_id", "not_found", "Folder not found")])
        if target.archived_at is not None:
            raise Conflict("The folder is archived", code="folder_archived")
        repo.adjust_case_count(s, case.folder_id, -1)
        repo.adjust_case_count(s, target.id, +1)
        changes["folder_id"] = [str(case.folder_id), str(target.id)]
        case.folder_id = target.id
        moved = True
    if "tags" in fields:
        before = repo.tag_names_of(s, [case.id])[case.id]
        after_ids = _resolve_tags(uow, ctx, fields["tags"])
        after = sorted({t.strip().lower() for t in fields["tags"] if t.strip()})
        if before != after:
            repo.set_case_tags(s, case.id, after_ids)
            changes["tags"] = [before, after]
    if "automation_keys" in fields:
        before_keys = repo.automation_keys_of(s, [case.id])[case.id]
        after_keys = sorted({k.strip() for k in fields["automation_keys"] if k.strip()})
        if before_keys != after_keys:
            _set_keys(uow, ctx, case.id, after_keys)
            changes["automation_keys"] = [before_keys, after_keys]
    if changes:
        _touch(case, ctx)
        action = "test_case.moved" if moved and list(changes) == ["folder_id"] else "test_case.updated"
        uow.audit(ctx, action, case, changes=changes)
    return case


def _j(v: Any) -> Any:
    return v.value if hasattr(v, "value") else (str(v) if isinstance(v, UUID) else v)


# -- review workflow (FR-TD-006, BR-17/18) --------------------------------------------------------


def _latest(uow: UnitOfWork, ctx: AccessContext, case: TestCase) -> TestCaseVersion:
    v = (
        repo.version(uow.session, ctx, case.latest_version_id, for_update=True)
        if case.latest_version_id
        else None
    )
    assert v is not None
    return v


def _record_comment(uow: UnitOfWork, ctx: AccessContext, case: TestCase, body: str | None) -> None:
    """AC-TD-22: review comments are shown on the case (the audit event names the version)."""
    if body and body.strip():
        from tcms.platform import comments

        members = {
            m.user.id
            for m in identity_queries.project_members(uow.session, ctx.principal.organization_id, ctx.pid)
        }
        comments.add_comment(uow, ctx, case_record(case), body, members=members, require=False)


def submit_for_review(
    uow: UnitOfWork, ctx: AccessContext, case_id: UUID, *, reviewer_id: UUID | None, comment: str | None
) -> TestCase:
    """US-065: draft → in_review; the reviewer (or every approver) is notified."""
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.edit")
    flags = _flags(uow, ctx)
    if not rules.transition_allowed("submit", case.status, approval_required=flags.approval_required):
        raise InvalidStatus("Only draft cases can be submitted while approval is required")
    if reviewer_id is not None:
        _check_people(uow, ctx, None, reviewer_id)
        case.reviewer_id = reviewer_id
    v = _latest(uow, ctx, case)
    v.submitted_by = _uid(ctx)
    v.submitted_at = clock.now()
    case.status = CaseStatus.in_review
    _touch(case, ctx)
    _record_comment(uow, ctx, case, comment)
    uow.audit(
        ctx,
        "test_case.submitted",
        case,
        changes={"status": ["draft", "in_review"], "version": [None, v.version_no]},
    )
    recipients = (
        {case.reviewer_id}
        if case.reviewer_id
        else {
            u.id
            for u in identity_queries.members_with_permission(
                uow.session, ctx.principal.organization_id, ctx.pid, "testcase.approve"
            )
        }
    )
    notifications.notify(
        uow,
        organization_id=ctx.principal.organization_id,
        user_ids=recipients,
        type="test_case.review_requested",
        project_id=ctx.pid,
        entity_type="test_case",
        entity_id=case.id,
        payload={
            "key": case.key,
            "title": case.title,
            "version": v.version_no,
            "by": ctx.principal.display_name,
        },
        exclude=ctx.principal.user_id,
    )
    return case


def approve(
    uow: UnitOfWork, ctx: AccessContext, case_id: UUID, *, row_version: int, comment: str | None
) -> TestCase:
    """AC-TD-21: the author of the latest version may not approve it unless self-approval is allowed."""
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.approve")
    check_row_version(case.row_version, row_version)
    flags = _flags(uow, ctx)
    if not rules.transition_allowed("approve", case.status, approval_required=flags.approval_required):
        raise InvalidStatus("Only cases in review can be approved")
    v = _latest(uow, ctx, case)
    if rules.self_approval_blocked(
        author_id=v.created_by,
        approver_id=ctx.principal.user_id,
        allow_self_approval=flags.allow_self_approval,
    ):
        raise SelfApprovalNotAllowed()
    _approve_version(v, case, by=ctx.principal.user_id, mode=ApprovalMode.manual)
    case.status = CaseStatus.approved
    _touch(case, ctx)
    _record_comment(uow, ctx, case, comment)
    uow.audit(
        ctx,
        "test_case.approved",
        case,
        changes={"status": ["in_review", "approved"], "approved_version": [None, v.version_no]},
    )
    notifications.notify(
        uow,
        organization_id=ctx.principal.organization_id,
        user_ids={v.created_by},
        type="test_case.approved",
        project_id=ctx.pid,
        entity_type="test_case",
        entity_id=case.id,
        payload={"key": case.key, "version": v.version_no, "by": ctx.principal.display_name},
        exclude=ctx.principal.user_id,
    )
    return case


def return_case(uow: UnitOfWork, ctx: AccessContext, case_id: UUID, *, comment: str) -> TestCase:
    """AC-TD-22: in_review → draft; the comment is required, kept on the version, and the author notified."""
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.approve")
    if not comment or not comment.strip():
        raise ValidationFailed(
            "A comment is required", errors=[FieldError("comment", "required", "Say what to change")]
        )
    flags = _flags(uow, ctx)
    if not rules.transition_allowed("return", case.status, approval_required=flags.approval_required):
        raise InvalidStatus("Only cases in review can be returned")
    v = _latest(uow, ctx, case)
    case.status = CaseStatus.draft
    _touch(case, ctx)
    _record_comment(uow, ctx, case, comment)
    uow.audit(
        ctx,
        "test_case.returned",
        case,
        changes={"status": ["in_review", "draft"]},
        extra={"reason": comment.strip()[:1000]},
    )
    notifications.notify(
        uow,
        organization_id=ctx.principal.organization_id,
        user_ids={v.created_by},
        type="test_case.returned",
        project_id=ctx.pid,
        entity_type="test_case",
        entity_id=case.id,
        payload={
            "key": case.key,
            "version": v.version_no,
            "by": ctx.principal.display_name,
            "comment": comment.strip()[:500],
        },
        exclude=ctx.principal.user_id,
    )
    return case


# -- lifecycle (FR-TD-007, BR-13, BR-14) ----------------------------------------------------------


def change_lifecycle(
    uow: UnitOfWork,
    ctx: AccessContext,
    case_id: UUID,
    *,
    action: Literal["deprecate", "archive", "restore"],
    reason: str | None,
) -> TestCase:
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.archive")
    flags = _flags(uow, ctx)
    if not rules.transition_allowed(action, case.status, approval_required=flags.approval_required):
        raise InvalidStatus(f"Cannot {action} a case that is {case.status.value}")
    old = case.status
    if action == "deprecate":
        case.status = CaseStatus.deprecated
    elif action == "archive":
        case.status = CaseStatus.archived
        case.archived_at, case.archived_by = clock.now(), ctx.principal.user_id
        repo.adjust_case_count(uow.session, case.folder_id, -1)
    else:
        if old is CaseStatus.archived:
            repo.adjust_case_count(uow.session, case.folder_id, +1)
            case.archived_at = case.archived_by = None
        case.status = rules.status_after_restore(
            approval_required=flags.approval_required,
            latest_is_approved=case.approved_version_id == case.latest_version_id,
        )
    _touch(case, ctx)
    extra = {"reason": reason.strip()[:1000]} if reason and reason.strip() else None
    verb = {"deprecate": "deprecated", "archive": "archived", "restore": "restored"}[action]
    uow.audit(ctx, f"test_case.{verb}", case, changes={"status": [old.value, case.status.value]}, extra=extra)
    return case


def delete_case(uow: UnitOfWork, ctx: AccessContext, case_id: UUID) -> None:
    """BR-14: hard delete only if never included in a run; the key is never reused (BR-16)."""
    s = uow.session
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.delete")
    step_ids = [st.id for v in repo.versions(s, ctx, case.id) for st in repo.steps_of(s, [v.id])[v.id]]
    attachments.remove_links_of(uow, ctx.principal.organization_id, "test_case", [case.id])
    attachments.remove_links_of(uow, ctx.principal.organization_id, "test_case_step", step_ids)
    if case.status is not CaseStatus.archived:
        repo.adjust_case_count(s, case.folder_id, -1)
    uow.audit(
        ctx,
        "test_case.deleted",
        case,
        summary=f"{ctx.principal.display_name} deleted {case.key} {case.title}",
    )
    s.flush()
    try:
        with s.begin_nested():
            repo.purge(s, case.id)
    except DBAPIError as exc:
        if "case_has_runs" in str(exc.orig):
            raise CaseHasRuns() from exc
        raise
    s.expunge(case)


def duplicate_case(
    uow: UnitOfWork,
    ctx: AccessContext,
    case_id: UUID,
    *,
    folder_id: UUID | None,
    title: str | None,
    store: attachments.Storage | None,
) -> SaveResult:
    """FR-TD-009: new key, v1 = latest content, same metadata, attachments copied, link duplicated_from."""
    ctx.require("testcase.create")
    s = uow.session
    src = repo.case_(s, ctx, case_id)
    if src is None:
        raise NotFound()
    latest = repo.version(s, ctx, src.latest_version_id) if src.latest_version_id else None
    assert latest is not None
    content = _version_content(uow, latest)
    target_folder = folder_id or src.folder_id
    from dataclasses import replace

    new_title = (
        title or rules.duplicate_title(src.title, same_folder=target_folder == src.folder_id)
    ).strip()
    meta = CaseMetadata(
        folder_id=target_folder,
        type=src.type,
        design_technique=src.design_technique,
        priority=src.priority,
        tags=repo.tag_names_of(s, [src.id])[src.id],
        owner_id=_uid(ctx),
        reviewer_id=src.reviewer_id,
        automation_status=src.automation_status,
        automation_keys=[],
        estimated_minutes=src.estimated_minutes,
    )
    result = create_case(uow, ctx, content=replace(content, title=new_title), meta=meta)
    new = result.case
    s.add(
        TestCaseLink(
            id=ids.new_id(),
            organization_id=new.organization_id,
            project_id=new.project_id,
            source_case_id=new.id,
            target_case_id=src.id,
            link_type=CaseLinkType.duplicated_from,
            created_at=clock.now(),
            created_by=ctx.principal.user_id,
        )
    )
    if store is not None:
        case_atts = attachments.list_for(uow, ctx.principal.organization_id, "test_case", [src.id])[src.id]
        attachments.copy_to(uow, ctx, case_atts, case_record(new), store)
        old_steps = repo.steps_of(s, [latest.id])[latest.id]
        new_steps = (
            repo.steps_of(s, [new.latest_version_id])[new.latest_version_id] if new.latest_version_id else []
        )
        step_atts = attachments.list_for(
            uow, ctx.principal.organization_id, "test_case_step", [x.id for x in old_steps]
        )
        for old, fresh in zip(old_steps, new_steps, strict=False):
            if step_atts.get(old.id):
                attachments.copy_to(uow, ctx, step_atts[old.id], step_record(new, fresh), store)
    uow.audit(ctx, "test_case.duplicated", new, changes={"duplicated_from": [None, src.key]})
    return result


# -- related links (FR-TD-012) --------------------------------------------------------------------


def add_link(
    uow: UnitOfWork, ctx: AccessContext, case_id: UUID, *, target_case_id: UUID, link_type: CaseLinkType
) -> None:
    s = uow.session
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.edit")
    target = repo.case_(s, ctx, target_case_id)
    if target is None:
        raise NotFound("Linked case not found")
    if target.id == case.id:
        raise ValidationFailed(
            errors=[FieldError("target_case_id", "self", "A case cannot be linked to itself")]
        )
    if len(repo.links_of(s, ctx, case.id)) >= rules.MAX_LINKS:
        raise Conflict("At most 50 links per case", code="link_limit")
    source, dest = (
        rules.ordered_pair(case.id, target.id) if link_type is CaseLinkType.related else (case.id, target.id)
    )
    if repo.link(s, ctx, source, dest, link_type.value) is not None:  # type: ignore[arg-type]
        return
    s.add(
        TestCaseLink(
            id=ids.new_id(),
            organization_id=case.organization_id,
            project_id=case.project_id,
            source_case_id=source,
            target_case_id=dest,
            link_type=link_type,
            created_at=clock.now(),
            created_by=ctx.principal.user_id,
        )
    )
    uow.audit(ctx, "test_case.link_added", case, changes={"link": [None, f"{link_type.value}:{target.key}"]})


def remove_link(
    uow: UnitOfWork, ctx: AccessContext, case_id: UUID, *, target_case_id: UUID, link_type: CaseLinkType
) -> None:
    s = uow.session
    case = _case(uow, ctx, case_id)
    ctx.require("testcase.edit")
    target = repo.case_(s, ctx, target_case_id)
    if target is None:
        raise NotFound()
    candidates = (
        [rules.ordered_pair(case.id, target.id)]
        if link_type is CaseLinkType.related
        else [(case.id, target.id), (target.id, case.id)]
    )
    for a, b in candidates:
        row = repo.link(s, ctx, a, b, link_type.value)  # type: ignore[arg-type]
        if row is not None:
            s.delete(row)
            uow.audit(
                ctx,
                "test_case.link_removed",
                case,
                changes={"link": [f"{link_type.value}:{target.key}", None]},
            )
            return
    raise NotFound("Link not found")


# -- tags (FR-TD-008) -----------------------------------------------------------------------------


def create_tag(uow: UnitOfWork, ctx: AccessContext, name: str) -> Tag:
    ctx.require("testcase.edit")
    name = name.strip().lower()
    problems = rules.tag_problems([name])
    if problems:
        raise ValidationFailed("Invalid tag", errors=problems)
    if repo.tags_by_name(uow.session, ctx, [name]):
        raise NameTaken("This tag already exists")
    t = Tag(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        name=name,
        is_system=False,
        created_at=clock.now(),
        created_by=ctx.principal.user_id,
    )
    uow.session.add(t)
    uow.session.flush()
    uow.audit(ctx, "tag.created", AuditTarget("tag", t.id, name))
    return t


def delete_tag(uow: UnitOfWork, ctx: AccessContext, tag_id: UUID) -> None:
    ctx.require("testcase.edit")
    t = repo.tag(uow.session, ctx, tag_id)
    if t is None:
        raise NotFound()
    if t.is_system:
        raise Conflict("System tags cannot be deleted", code="system_tag")
    if repo.tag_in_use(uow.session, t.id):
        raise Conflict("Only unused tags can be deleted", code="tag_in_use")
    uow.audit(ctx, "tag.deleted", AuditTarget("tag", t.id, t.name))
    uow.session.delete(t)


# -- bulk (FR-TD-010) -----------------------------------------------------------------------------

BulkAction = Literal[
    "move",
    "add_tags",
    "remove_tags",
    "set_priority",
    "set_type",
    "set_owner",
    "set_reviewer",
    "set_automation_status",
    "deprecate",
    "archive",
    "restore",
]
BULK_MAX = 5000
BULK_SYNC_LIMIT = 200
_BULK_PERMISSION = {
    "deprecate": "testcase.archive",
    "archive": "testcase.archive",
    "restore": "testcase.archive",
}


@dataclass(frozen=True)
class BulkResult:
    updated: int
    skipped: list[dict[str, str]]


def bulk_permission(action: str) -> str:
    return _BULK_PERMISSION.get(action, "testcase.edit")


def apply_bulk(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    action: BulkAction,
    case_ids: list[UUID],
    params: dict[str, Any],
    bulk_id: UUID,
) -> BulkResult:
    """Each case is changed through the regular service function and audited with the shared bulk id."""
    ctx.require(bulk_permission(action))
    uow.bulk_operation_id = bulk_id
    updated, skipped = 0, []
    s = uow.session
    for case in repo.cases_by_ids(s, ctx, case_ids):
        try:
            with s.begin_nested():
                if action == "move":
                    update_metadata(
                        uow,
                        ctx,
                        case.id,
                        row_version=None,
                        fields={"folder_id": UUID(str(params["folder_id"]))},
                        bulk=True,
                    )
                elif action in ("add_tags", "remove_tags"):
                    current = set(repo.tag_names_of(s, [case.id])[case.id])
                    change = {t.strip().lower() for t in params.get("tags", [])}
                    new = current | change if action == "add_tags" else current - change
                    update_metadata(
                        uow, ctx, case.id, row_version=None, fields={"tags": sorted(new)}, bulk=True
                    )
                elif action in ("deprecate", "archive", "restore"):
                    change_lifecycle(uow, ctx, case.id, action=action, reason=params.get("reason"))
                else:
                    name = {
                        "set_priority": "priority",
                        "set_type": "type",
                        "set_owner": "owner_id",
                        "set_reviewer": "reviewer_id",
                        "set_automation_status": "automation_status",
                    }[action]
                    value = params.get("value")
                    if name in ("owner_id", "reviewer_id") and value is not None:
                        value = UUID(str(value))
                    elif name == "priority":
                        value = PriorityLevel(str(value))
                    elif name == "type":
                        value = CaseType(str(value))
                    elif name == "automation_status":
                        value = AutomationStatus(str(value))
                    update_metadata(uow, ctx, case.id, row_version=None, fields={name: value}, bulk=True)
                updated += 1
        except (ValidationFailed, Conflict, InvalidStatus, CaseArchived, NotFound) as exc:
            skipped.append({"key": case.key, "code": exc.code, "detail": exc.detail})
        except (ValueError, KeyError) as exc:
            skipped.append({"key": case.key, "code": "invalid_params", "detail": str(exc)})
    return BulkResult(updated, skipped)


# -- records for attachments and comments ---------------------------------------------------------


def case_record(case: TestCase) -> RecordRef:
    return RecordRef("test_case", case.id, case.project_id, case.key, "testcase.edit")


def version_record(case: TestCase, v: TestCaseVersion) -> RecordRef:
    return RecordRef(
        "test_case_version", v.id, case.project_id, f"{case.key} v{v.version_no}", "comment.create"
    )


def step_record(case: TestCase, st: TestCaseStep, *, approved: bool = False) -> RecordRef:
    # BR-28: step attachments of an approved version can no longer be removed.
    return RecordRef(
        "test_case_step",
        st.id,
        case.project_id,
        f"{case.key} step {st.position}",
        "testcase.edit",
        immutable=approved,
    )


def resolve_record(uow: UnitOfWork, ctx: AccessContext, entity_type: str, entity_id: UUID) -> RecordRef:
    s = uow.session
    if entity_type == "test_case":
        case = repo.case_(s, ctx, entity_id)
        if case is None:
            raise NotFound()
        return case_record(case)
    if entity_type == "test_case_version":
        v = repo.version(s, ctx, entity_id)
        case = repo.case_(s, ctx, v.test_case_id) if v else None
        if v is None or case is None:
            raise NotFound()
        return version_record(case, v)
    if entity_type == "test_case_step":
        st = repo.step(s, ctx, entity_id)
        v = repo.version(s, ctx, st.version_id) if st else None
        case = repo.case_(s, ctx, v.test_case_id) if v else None
        if st is None or v is None or case is None:
            raise NotFound()
        # BR-28: steps of a manually approved (reviewed) version, and of older versions (history), keep their
        # attachments. With approval disabled every save is auto-approved, so "approved" means reviewed here.
        reviewed = v.approval_mode is ApprovalMode.manual
        return step_record(case, st, approved=reviewed or v.id != case.latest_version_id)
    raise NotFound()


# -- event handlers -------------------------------------------------------------------------------


@subscribe(ProjectCreated)
def create_system_tags(uow: UnitOfWork, event: ProjectCreated) -> None:
    """In-transaction handler (docs/03 §5.4): every project starts with the system tags."""
    now = clock.now()
    for name in rules.SYSTEM_TAGS:
        uow.session.add(
            Tag(
                id=ids.new_id(),
                organization_id=event.organization_id,
                project_id=event.project_id,
                name=name,
                is_system=True,
                created_at=now,
                created_by=event.actor_id,
            )
        )


@subscribe(ApprovalSettingChanged)
def apply_approval_toggle(uow: UnitOfWork, event: ApprovalSettingChanged) -> None:
    """US-067 (TCMS-040): on → grandfathered (no change); off → draft/in_review auto-approved at latest."""
    if event.now_required:
        return
    from sqlalchemy import select

    from tcms.testdesign.models import TestCase as TC

    rows = uow.session.execute(
        select(TC)
        .where(
            TC.organization_id == event.organization_id,
            TC.project_id == event.project_id,
            TC.status.in_([CaseStatus.draft, CaseStatus.in_review]),
        )
        .with_for_update()
    ).scalars()
    for case in rows:
        new_status, approve_latest = rules.status_when_approval_toggled(case.status, now_required=False)
        if approve_latest and case.latest_version_id:
            v = uow.session.get(TestCaseVersion, case.latest_version_id)
            if v is not None and v.approved_at is None:
                _approve_version(v, case, by=None, mode=ApprovalMode.auto)
        case.status = new_status
        case.row_version += 1
