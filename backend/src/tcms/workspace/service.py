"""Workspace use cases (docs/02 §4): organization, projects, environments, releases, human keys."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from tcms.core import clock, ids
from tcms.core.concurrency import check_row_version
from tcms.core.context import AccessContext
from tcms.core.enums import ProjectStatus, ReleaseStatus
from tcms.core.errors import FieldError, NotFound, ValidationFailed
from tcms.core.events import DomainEvent
from tcms.core.permissions import RoleCode
from tcms.core.policy import OrgPolicy
from tcms.core.uow import UnitOfWork
from tcms.identity import service as identity
from tcms.workspace import repository as repo
from tcms.workspace import rules
from tcms.workspace.errors import ConfirmationMismatch, InvalidTransition, NameTaken, ProjectKeyTaken
from tcms.workspace.models import Environment, KeySequence, Organization, Project, Release


@dataclass(frozen=True)
class ApprovalSettingChanged(DomainEvent):
    """US-067: testdesign grandfathers (on) or auto-approves draft/in-review cases (off), same transaction."""

    organization_id: UUID
    project_id: UUID
    now_required: bool
    actor_id: UUID | None


@dataclass(frozen=True)
class ProjectCreated(DomainEvent):
    organization_id: UUID
    project_id: UUID
    actor_id: UUID | None


def _touch(row: Any, ctx: AccessContext) -> None:
    row.updated_at = clock.now()
    row.updated_by = ctx.principal.user_id
    row.row_version += 1


def _org_id(ctx: AccessContext) -> UUID:
    return ctx.principal.organization_id


def _require_project(ctx: AccessContext) -> UUID:
    if ctx.project_id is None:
        raise RuntimeError("project context required")
    return ctx.project_id


# -- organization ---------------------------------------------------------------------------------


def create_organization(uow: UnitOfWork, *, name: str, slug: str) -> Organization:
    """US-020 (`tcms bootstrap`). No actor yet: the first admin is invited right after."""
    slug = slug.strip().lower()
    if not rules.SLUG_RE.match(slug):
        raise ValidationFailed(
            "Invalid slug", errors=[FieldError("slug", "invalid_format", "a-z, 0-9 and -")]
        )
    if not 1 <= len(name.strip()) <= 100:
        raise ValidationFailed(
            "Invalid name", errors=[FieldError("name", "invalid_length", "1–100 characters")]
        )
    if repo.organization_by_slug(uow.session, slug) is not None:
        raise NameTaken("An organization with this slug already exists")
    now = clock.now()
    org = Organization(
        id=ids.new_id(), name=name.strip(), slug=slug, settings={}, created_at=now, updated_at=now
    )
    uow.session.add(org)
    uow.session.flush()
    return org


def update_organization(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    row_version: int | None,
    name: str | None,
    settings: dict[str, Any] | None,
) -> Organization:
    """US-021: validation ranges per docs/02 §4.1; audit `organization.updated`."""
    ctx.require("org.manage")
    org = repo.organization(uow.session, _org_id(ctx), for_update=True)
    if org is None:
        raise NotFound()
    check_row_version(org.row_version, row_version)
    changes: dict[str, list[Any]] = {}
    if name is not None:
        if not 1 <= len(name.strip()) <= 100:
            raise ValidationFailed(errors=[FieldError("name", "invalid_length", "1–100 characters")])
        if name.strip() != org.name:
            changes["name"] = [org.name, name.strip()]
            org.name = name.strip()
    if settings:
        problems = rules.org_settings_problems(settings)
        if problems:
            raise ValidationFailed("Invalid settings", errors=problems)
        merged = rules.merged_org_settings(org.settings, settings)
        for key, value in settings.items():
            old = rules.merged_org_settings(org.settings, {}).get(key)
            if old != value:
                changes[f"settings.{key}"] = [old, value]
        org.settings = merged
    if changes:
        _touch(org, ctx)
        uow.audit(ctx, "organization.updated", org, changes=changes)
    return org


# -- projects -------------------------------------------------------------------------------------


def create_project(
    uow: UnitOfWork, ctx: AccessContext, *, key: str, name: str, description: str | None, policy: OrgPolicy
) -> Project:
    """US-022 / FR-WS-002: creator becomes QA Manager; QA + Staging environments; key sequences."""
    ctx.require("project.create")
    s = uow.session
    org_id = _org_id(ctx)
    key = rules.normalize_project_key(key)
    problem = rules.project_key_problem(key)
    if problem:
        raise ValidationFailed("Invalid project key", errors=[problem])
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise ValidationFailed(errors=[FieldError("name", "invalid_length", "1–100 characters")])
    if repo.project_by_key(s, org_id, key) is not None:
        raise ProjectKeyTaken(f"Project key {key} is already used")
    if repo.active_project_named(s, org_id, name) is not None:
        raise NameTaken("A project with this name already exists")
    now = clock.now()
    project = Project(
        id=ids.new_id(),
        organization_id=org_id,
        key=key,
        name=name,
        description=description,
        status=ProjectStatus.active,
        settings=rules.default_project_settings(policy),
        created_at=now,
        created_by=ctx.principal.user_id,
        updated_at=now,
        updated_by=ctx.principal.user_id,
    )
    s.add(project)
    s.flush()
    for entity in rules.KEY_ENTITIES:
        s.add(KeySequence(project_id=project.id, entity=entity, next_value=1))
    for env_name in rules.DEFAULT_ENVIRONMENTS:
        s.add(
            Environment(
                id=ids.new_id(),
                organization_id=org_id,
                project_id=project.id,
                name=env_name,
                created_at=now,
                created_by=ctx.principal.user_id,
                updated_at=now,
                updated_by=ctx.principal.user_id,
            )
        )
    s.flush()
    project_ctx = AccessContext(
        principal=ctx.principal,
        project_id=project.id,
        permissions=frozenset(),
        request_id=ctx.request_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        project_status=ProjectStatus.active.value,
    )
    uow.audit(project_ctx, "project.created", project, changes={"key": [None, key], "name": [None, name]})
    if ctx.principal.user_id is not None:
        identity.add_member(
            uow,
            project_ctx,
            user_id=ctx.principal.user_id,
            role_code=RoleCode.qa_manager.value,
            require_permission=False,
        )
    uow.emit(ProjectCreated(org_id, project.id, ctx.principal.user_id))
    return project


def get_project(uow: UnitOfWork, ctx: AccessContext) -> Project:
    project = repo.project(uow.session, _org_id(ctx), _require_project(ctx))
    if project is None:
        raise NotFound()
    return project


def update_project(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    row_version: int | None,
    name: str | None,
    description: str | None,
    description_set: bool,
    settings: dict[str, Any] | None,
    policy: OrgPolicy,
) -> Project:
    """US-023 / FR-WS-004. Settings changes are audited as `project.settings_changed`."""
    ctx.require("project.configure")
    s = uow.session
    project = repo.project(s, _org_id(ctx), _require_project(ctx), for_update=True)
    if project is None:
        raise NotFound()
    check_row_version(project.row_version, row_version)
    changes: dict[str, list[Any]] = {}
    if name is not None and name.strip() != project.name:
        new = name.strip()
        if not 1 <= len(new) <= 100:
            raise ValidationFailed(errors=[FieldError("name", "invalid_length", "1–100 characters")])
        if repo.active_project_named(s, project.organization_id, new, exclude=project.id) is not None:
            raise NameTaken("A project with this name already exists")
        changes["name"] = [project.name, new]
        project.name = new
    if description_set and description != project.description:
        changes["description"] = [project.description, description]
        project.description = description
    setting_changes: dict[str, list[Any]] = {}
    if settings:
        problems = rules.project_settings_problems(settings, policy)
        if problems:
            raise ValidationFailed("Invalid settings", errors=problems)
        current = rules.merged_project_settings(project.settings, {})
        for key, value in settings.items():
            if current.get(key) != value:
                setting_changes[key] = [current.get(key), value]
        project.settings = rules.merged_project_settings(project.settings, settings)
    if changes or setting_changes:
        _touch(project, ctx)
    if changes:
        uow.audit(ctx, "project.updated", project, changes=changes)
    if setting_changes:
        uow.audit(ctx, "project.settings_changed", project, changes=setting_changes)
    if "approval_required" in setting_changes:
        uow.emit(
            ApprovalSettingChanged(
                project.organization_id,
                project.id,
                bool(setting_changes["approval_required"][1]),
                ctx.principal.user_id,
            )
        )
    return project


def archive_project(uow: UnitOfWork, ctx: AccessContext, *, confirm_key: str) -> Project:
    """US-029. Typing the key confirms. (M3 adds: all cycles must be closed, review K17k.)"""
    ctx.require("project.configure")
    project = repo.project(uow.session, _org_id(ctx), _require_project(ctx), for_update=True)
    if project is None:
        raise NotFound()
    if confirm_key.strip().upper() != project.key:
        raise ConfirmationMismatch("Type the project key to confirm")
    if project.status is ProjectStatus.archived:
        return project
    project.status = ProjectStatus.archived
    project.archived_at = clock.now()
    project.archived_by = ctx.principal.user_id
    _touch(project, ctx)
    uow.audit(ctx, "project.archived", project, changes={"status": ["active", "archived"]})
    return project


def restore_project(uow: UnitOfWork, ctx: AccessContext) -> Project:
    ctx.require("project.configure")
    s = uow.session
    project = repo.project(s, _org_id(ctx), _require_project(ctx), for_update=True)
    if project is None:
        raise NotFound()
    if project.status is ProjectStatus.active:
        return project
    if repo.active_project_named(s, project.organization_id, project.name, exclude=project.id) is not None:
        raise NameTaken("An active project already uses this name; rename it first")
    project.status = ProjectStatus.active
    project.archived_at = None
    project.archived_by = None
    _touch(project, ctx)
    uow.audit(ctx, "project.restored", project, changes={"status": ["archived", "active"]})
    return project


def allocate_key(uow: UnitOfWork, ctx: AccessContext, entity: str) -> tuple[int, str]:
    """BR-16: next human key for `entity` in the context project (e.g. `SPARK-TC-1042`)."""
    project = get_project(uow, ctx)
    number = repo.next_key_number(uow.session, project.id, entity)
    return number, rules.human_key(project.key, entity, number)


# -- environments (FR-WS-005) ---------------------------------------------------------------------


def _env_name(name: str) -> str:
    name = name.strip()
    if not 1 <= len(name) <= 50:
        raise ValidationFailed(errors=[FieldError("name", "invalid_length", "1–50 characters")])
    return name


def create_environment(
    uow: UnitOfWork, ctx: AccessContext, *, name: str, description: str | None
) -> Environment:
    ctx.require("project.configure")
    project_id = _require_project(ctx)
    name = _env_name(name)
    if repo.environment_named(uow.session, project_id, name) is not None:
        raise NameTaken("An environment with this name already exists")
    now = clock.now()
    env = Environment(
        id=ids.new_id(),
        organization_id=_org_id(ctx),
        project_id=project_id,
        name=name,
        description=description,
        created_at=now,
        created_by=ctx.principal.user_id,
        updated_at=now,
        updated_by=ctx.principal.user_id,
    )
    uow.session.add(env)
    uow.session.flush()
    uow.audit(
        ctx,
        "environment.created",
        env,
        changes={"name": [None, name]},
        summary=f"{ctx.principal.display_name} added environment {name}",
    )
    return env


def _environment(uow: UnitOfWork, ctx: AccessContext, env_id: UUID) -> Environment:
    env = repo.environment(uow.session, _org_id(ctx), env_id, for_update=True)
    if env is None or env.project_id != ctx.project_id:
        raise NotFound()
    return env


def update_environment(
    uow: UnitOfWork,
    ctx: AccessContext,
    env_id: UUID,
    *,
    row_version: int | None,
    name: str | None,
    description: str | None,
    description_set: bool,
) -> Environment:
    ctx.require("project.configure")
    env = _environment(uow, ctx, env_id)
    check_row_version(env.row_version, row_version)
    changes: dict[str, list[Any]] = {}
    if name is not None and name.strip() != env.name:
        new = _env_name(name)
        if repo.environment_named(uow.session, env.project_id, new, exclude=env.id) is not None:
            raise NameTaken("An environment with this name already exists")
        changes["name"] = [env.name, new]
        env.name = new
    if description_set and description != env.description:
        changes["description"] = [env.description, description]
        env.description = description
    if changes:
        _touch(env, ctx)
        uow.audit(ctx, "environment.updated", env, changes=changes)
    return env


def set_environment_archived(
    uow: UnitOfWork, ctx: AccessContext, env_id: UUID, *, archived: bool
) -> Environment:
    """AC-WS-03: archived environments keep working in existing cycles; not selectable for new ones."""
    ctx.require("project.configure")
    env = _environment(uow, ctx, env_id)
    if (env.archived_at is not None) == archived:
        return env
    env.archived_at = clock.now() if archived else None
    env.archived_by = ctx.principal.user_id if archived else None
    _touch(env, ctx)
    uow.audit(ctx, "environment.archived" if archived else "environment.restored", env, summary=None)
    return env


# -- releases (FR-WS-006) -------------------------------------------------------------------------


def _release_fields(name: str | None, start: date | None, target: date | None) -> None:
    if name is not None and not 1 <= len(name.strip()) <= 50:
        raise ValidationFailed(errors=[FieldError("name", "invalid_length", "1–50 characters")])
    if start is not None and target is not None and target < start:
        raise ValidationFailed(
            errors=[FieldError("target_date", "before_start", "Target date must be on or after start")]
        )


def create_release(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    name: str,
    description: str | None,
    start_date: date | None,
    target_date: date | None,
) -> Release:
    ctx.require("release.manage")
    project_id = _require_project(ctx)
    _release_fields(name, start_date, target_date)
    name = name.strip()
    if repo.release_named(uow.session, project_id, name) is not None:
        raise NameTaken("A release with this name already exists")
    now = clock.now()
    rel = Release(
        id=ids.new_id(),
        organization_id=_org_id(ctx),
        project_id=project_id,
        name=name,
        description=description,
        status=ReleaseStatus.planned,
        start_date=start_date,
        target_date=target_date,
        created_at=now,
        created_by=ctx.principal.user_id,
        updated_at=now,
        updated_by=ctx.principal.user_id,
    )
    uow.session.add(rel)
    uow.session.flush()
    uow.audit(
        ctx,
        "release.created",
        rel,
        changes={"name": [None, name]},
        summary=f"{ctx.principal.display_name} created release {name}",
    )
    return rel


def update_release(
    uow: UnitOfWork,
    ctx: AccessContext,
    release_id: UUID,
    *,
    row_version: int | None,
    fields: dict[str, Any],
) -> Release:
    """Fields: name, description, start_date, target_date, status (valid transitions only, TCMS-024)."""
    ctx.require("release.manage")
    rel = repo.release(uow.session, _org_id(ctx), release_id, for_update=True)
    if rel is None or rel.project_id != ctx.project_id:
        raise NotFound()
    check_row_version(rel.row_version, row_version)
    start = fields.get("start_date", rel.start_date)
    target = fields.get("target_date", rel.target_date)
    _release_fields(fields.get("name"), start, target)
    changes: dict[str, list[Any]] = {}
    if "name" in fields and fields["name"].strip() != rel.name:
        new = fields["name"].strip()
        if repo.release_named(uow.session, rel.project_id, new, exclude=rel.id) is not None:
            raise NameTaken("A release with this name already exists")
        changes["name"] = [rel.name, new]
        rel.name = new
    for key in ("description", "start_date", "target_date"):
        if key in fields and fields[key] != getattr(rel, key):
            changes[key] = [_jsonable(getattr(rel, key)), _jsonable(fields[key])]
            setattr(rel, key, fields[key])
    if "status" in fields and fields["status"] != rel.status:
        target_status = ReleaseStatus(fields["status"])
        if not rules.release_transition_allowed(rel.status, target_status):
            allowed = ", ".join(sorted(s.value for s in rules.allowed_release_targets(rel.status))) or "none"
            raise InvalidTransition(
                f"Cannot move from {rel.status.value} to {target_status.value} (allowed: {allowed})"
            )
        changes["status"] = [rel.status.value, target_status.value]
        rel.status = target_status
        if target_status is ReleaseStatus.released:
            rel.released_at = clock.now()
        if target_status is ReleaseStatus.archived:
            rel.archived_at = clock.now()
    if changes:
        _touch(rel, ctx)
        action = "release.status_changed" if list(changes) == ["status"] else "release.updated"
        uow.audit(ctx, action, rel, changes=changes)
    return rel


def _jsonable(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date) else v
