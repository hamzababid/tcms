"""Import mapping templates per project and entity (docs/02 §15.1, US-151; M8 D5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tcms.core import clock, ids
from tcms.core.context import AccessContext
from tcms.core.errors import FieldError, ValidationFailed
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.platform.models import ImportMapping


@dataclass(frozen=True)
class TemplateView:
    id: UUID
    entity: str
    name: str
    mapping: dict[str, Any]
    created_by: UUID | None
    created_at: datetime


def _view(m: ImportMapping) -> TemplateView:
    return TemplateView(m.id, m.entity, m.name, dict(m.mapping), m.created_by, m.created_at)


def list_for(uow: UnitOfWork, ctx: AccessContext, entity: str | None) -> list[TemplateView]:
    stmt = select(ImportMapping).where(
        ImportMapping.organization_id == ctx.principal.organization_id, ImportMapping.project_id == ctx.pid
    )
    if entity:
        stmt = stmt.where(ImportMapping.entity == entity)
    return [_view(m) for m in uow.session.execute(stmt.order_by(func.lower(ImportMapping.name))).scalars()]


def get(uow: UnitOfWork, ctx: AccessContext, template_id: UUID) -> TemplateView | None:
    m = uow.session.get(ImportMapping, template_id)
    if m is None or m.project_id != ctx.pid or m.organization_id != ctx.principal.organization_id:
        return None
    return _view(m)


def save(
    uow: UnitOfWork, ctx: AccessContext, *, entity: str, name: str, mapping: dict[str, Any]
) -> TemplateView:
    """Saving under an existing name (case-insensitive) replaces that template's mapping."""
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise ValidationFailed(errors=[FieldError("name", "invalid_length", "1–100 characters")])
    taken = uow.session.execute(
        select(ImportMapping).where(
            ImportMapping.project_id == ctx.pid,
            ImportMapping.entity == entity,
            func.lower(ImportMapping.name) == name.lower(),
        )
    ).scalar_one_or_none()
    if taken is not None:
        taken.mapping = mapping
        uow.audit(
            ctx,
            "import_mapping.updated",
            taken,
            summary=f"{ctx.principal.display_name} updated mapping {name}",
        )
        return _view(taken)
    m = ImportMapping(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        entity=entity,
        name=name,
        mapping=mapping,
        created_at=clock.now(),
        created_by=ctx.principal.user_id,
    )
    uow.session.add(m)
    uow.session.flush()
    uow.audit(ctx, "import_mapping.created", m, summary=f"{ctx.principal.display_name} saved mapping {name}")
    return _view(m)


def delete(uow: UnitOfWork, ctx: AccessContext, template_id: UUID) -> None:
    m = uow.session.get(ImportMapping, template_id)
    if m is None or m.project_id != ctx.pid:
        return
    uow.session.delete(m)
    uow.audit(
        ctx,
        "import_mapping.deleted",
        AuditTarget("import_mapping", m.id, m.name),
        summary=f"{ctx.principal.display_name} deleted mapping {m.name}",
    )


def owner_of(s: Session, template_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(ImportMapping.organization_id, ImportMapping.project_id).where(ImportMapping.id == template_id)
    ).first()
    return (row[0], row[1]) if row else None
