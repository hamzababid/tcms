"""Saved views (docs/02 §12, US-132): a list's filters, sort and columns under a name, private or shared.

`is_default` on a private view is the owner's default for that list; on a shared view it is the project
default for everyone without a private default. Sharing needs `cycle.manage`, `plan.manage` or
`project.configure`. Audit: `saved_view.created/updated/deleted`.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

from sqlalchemy import select, update

from tcms.core import clock, ids
from tcms.core.context import AccessContext
from tcms.core.enums import ViewVisibility
from tcms.core.errors import FieldError, NotFound, PermissionDenied, ValidationFailed
from tcms.core.uow import UnitOfWork
from tcms.platform.models import SavedView

ENTITY_TYPES: Final = frozenset({"test_case", "test_run", "test_plan", "test_cycle", "bug", "requirement"})
SHARE_PERMISSIONS: Final = ("cycle.manage", "plan.manage", "project.configure")
MAX_FILTERS: Final = 30


def can_share(ctx: AccessContext) -> bool:
    return any(ctx.has(p) for p in SHARE_PERMISSIONS)


def definition_problems(definition: dict[str, Any]) -> list[FieldError]:
    """{filters: {name: value}, sort, columns}; filter values are the list's query parameters."""
    problems: list[FieldError] = []
    unknown = set(definition) - {"filters", "sort", "columns"}
    if unknown:
        problems.append(
            FieldError("definition", "invalid_value", f"Unknown keys: {', '.join(sorted(unknown))}")
        )
    filters = definition.get("filters") or {}
    if not isinstance(filters, dict) or len(filters) > MAX_FILTERS:
        problems.append(
            FieldError("definition.filters", "invalid_value", f"An object with ≤ {MAX_FILTERS} filters")
        )
    else:
        for k, v in filters.items():
            limit = (
                4000 if k == "_ui" else 500
            )  # `_ui`: the screen's own filter state (JSON), not a query param
            if not isinstance(k, str) or not 1 <= len(k) <= 40 or not isinstance(v, str) or len(v) > limit:
                problems.append(FieldError(f"definition.filters.{k}", "invalid_value", "Text values only"))
                break
    sort = definition.get("sort")
    if sort is not None and (not isinstance(sort, str) or len(sort) > 100):
        problems.append(FieldError("definition.sort", "invalid_value", "A sort expression"))
    cols = definition.get("columns")
    if cols is not None and (
        not isinstance(cols, list)
        or len(cols) > 40
        or not all(isinstance(c, str) and len(c) <= 40 for c in cols)
    ):
        problems.append(FieldError("definition.columns", "invalid_value", "A list of column ids"))
    return problems


def _check(
    ctx: AccessContext, entity_type: str, name: str, visibility: ViewVisibility, definition: dict[str, Any]
) -> None:
    problems = definition_problems(definition)
    if entity_type not in ENTITY_TYPES:
        problems.append(FieldError("entity_type", "invalid_value", "Unknown list"))
    if not 1 <= len(name.strip()) <= 100:
        problems.append(FieldError("name", "invalid_length", "1–100 characters"))
    if problems:
        raise ValidationFailed("Check the view", errors=problems)
    if visibility == ViewVisibility.project and not can_share(ctx):
        raise PermissionDenied(
            "cycle.manage", "Sharing a view needs cycle.manage, plan.manage or project.configure"
        )


def _name_taken(
    uow: UnitOfWork, ctx: AccessContext, entity_type: str, name: str, exclude: UUID | None
) -> bool:
    from sqlalchemy import func

    stmt = select(SavedView.id).where(
        SavedView.project_id == ctx.pid,
        SavedView.owner_id == ctx.principal.user_id,
        SavedView.entity_type == entity_type,
        func.lower(SavedView.name) == name.strip().lower(),
    )
    if exclude is not None:
        stmt = stmt.where(SavedView.id != exclude)
    return uow.session.execute(stmt.limit(1)).first() is not None


def _clear_defaults(uow: UnitOfWork, ctx: AccessContext, view: SavedView) -> None:
    stmt = update(SavedView).where(
        SavedView.project_id == ctx.pid, SavedView.entity_type == view.entity_type, SavedView.id != view.id
    )
    if view.visibility == ViewVisibility.private:
        stmt = stmt.where(SavedView.owner_id == view.owner_id, SavedView.visibility == ViewVisibility.private)
    else:
        stmt = stmt.where(SavedView.visibility == ViewVisibility.project)
    uow.session.execute(stmt.values(is_default=False))


def create(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    entity_type: str,
    name: str,
    visibility: ViewVisibility,
    definition: dict[str, Any],
    is_default: bool,
) -> SavedView:
    ctx.require("project.view")
    if ctx.principal.user_id is None:
        raise PermissionDenied("project.view")
    _check(ctx, entity_type, name, visibility, definition)
    if _name_taken(uow, ctx, entity_type, name, None):
        from tcms.core.errors import Conflict

        raise Conflict("You already have a view with this name", code="name_taken")
    now = clock.now()
    view = SavedView(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        owner_id=ctx.principal.user_id,
        entity_type=entity_type,
        name=name.strip(),
        visibility=visibility,
        definition=definition,
        is_default=is_default,
        created_at=now,
        created_by=ctx.principal.user_id,
        updated_at=now,
        updated_by=ctx.principal.user_id,
    )
    uow.session.add(view)
    uow.session.flush()
    if is_default:
        _clear_defaults(uow, ctx, view)
    uow.audit(
        ctx, "saved_view.created", view, extra={"entity_type": entity_type, "visibility": visibility.value}
    )
    return view


def _own(uow: UnitOfWork, ctx: AccessContext, view_id: UUID) -> SavedView:
    view = uow.session.execute(
        select(SavedView).where(SavedView.id == view_id, SavedView.project_id == ctx.pid).with_for_update()
    ).scalar_one_or_none()
    if view is None or (view.owner_id != ctx.principal.user_id and view.visibility == ViewVisibility.private):
        raise NotFound()
    if view.owner_id != ctx.principal.user_id:
        raise PermissionDenied("owner", "Only the owner can change this view")
    return view


def update_view(uow: UnitOfWork, ctx: AccessContext, view_id: UUID, *, fields: dict[str, Any]) -> SavedView:
    view = _own(uow, ctx, view_id)
    name = fields.get("name", view.name)
    visibility = ViewVisibility(fields.get("visibility", view.visibility))
    definition = fields.get("definition", view.definition)
    _check(ctx, view.entity_type, name, visibility, definition)
    if "name" in fields and _name_taken(uow, ctx, view.entity_type, name, view.id):
        from tcms.core.errors import Conflict

        raise Conflict("You already have a view with this name", code="name_taken")
    view.name, view.visibility, view.definition = name.strip(), visibility, definition
    if "is_default" in fields:
        view.is_default = bool(fields["is_default"])
    view.updated_at = clock.now()
    view.updated_by = ctx.principal.user_id
    view.row_version += 1
    uow.session.flush()
    if view.is_default:
        _clear_defaults(uow, ctx, view)
    uow.audit(
        ctx,
        "saved_view.updated",
        view,
        changes={k: [None, str(v)] for k, v in fields.items() if k != "definition"},
    )
    return view


def delete_view(uow: UnitOfWork, ctx: AccessContext, view_id: UUID) -> None:
    view = _own(uow, ctx, view_id)
    uow.audit(ctx, "saved_view.deleted", view)
    uow.session.delete(view)


def list_views(uow: UnitOfWork, ctx: AccessContext, entity_type: str | None) -> list[SavedView]:
    """Mine and the project's shared views; private defaults first, then shared defaults, then by name."""
    stmt = select(SavedView).where(
        SavedView.organization_id == ctx.principal.organization_id,
        SavedView.project_id == ctx.pid,
        (SavedView.owner_id == ctx.principal.user_id) | (SavedView.visibility == ViewVisibility.project),
    )
    if entity_type:
        stmt = stmt.where(SavedView.entity_type == entity_type)
    rows = list(uow.session.execute(stmt).scalars())
    mine = ctx.principal.user_id

    def order(v: SavedView) -> tuple[int, str]:
        rank = 0 if v.is_default and v.owner_id == mine and v.visibility == ViewVisibility.private else 1
        rank = rank if rank == 0 else (1 if v.is_default and v.visibility == ViewVisibility.project else 2)
        return rank, v.name.lower()

    return sorted(rows, key=order)


def visible_view(uow: UnitOfWork, ctx: AccessContext, view_id: UUID, *, entity_type: str) -> SavedView | None:
    """A view the caller may use: their own or a shared one of the project, for the given list."""
    view = uow.session.execute(
        select(SavedView).where(
            SavedView.id == view_id,
            SavedView.project_id == ctx.pid,
            SavedView.entity_type == entity_type,
            (SavedView.owner_id == ctx.principal.user_id) | (SavedView.visibility == ViewVisibility.project),
        )
    ).scalar_one_or_none()
    return view


def owner_of(s: Any, view_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(SavedView.organization_id, SavedView.project_id).where(SavedView.id == view_id)
    ).first()
    return (row[0], row[1]) if row else None
