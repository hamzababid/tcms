"""Bug-link data access (private to the module). Every query is organization- and project-scoped."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tcms.bugs.models import BugLink
from tcms.core.context import AccessContext


def _scope(ctx: AccessContext) -> Any:
    return select(BugLink).where(
        BugLink.organization_id == ctx.principal.organization_id, BugLink.project_id == ctx.pid
    )


def link(s: Session, ctx: AccessContext, link_id: UUID, *, for_update: bool = False) -> BugLink | None:
    stmt = _scope(ctx).where(BugLink.id == link_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def existing(
    s: Session,
    ctx: AccessContext,
    *,
    reference_norm: str,
    test_case_id: UUID,
    result_id: UUID | None,
    step_id: UUID | None,
) -> BugLink | None:
    """Same target as `ux_bug_links__target` (AC-BUG-06)."""
    stmt = _scope(ctx).where(
        BugLink.reference_norm == reference_norm,
        BugLink.test_case_id == test_case_id,
        BugLink.result_id.is_(None) if result_id is None else BugLink.result_id == result_id,
        BugLink.step_id.is_(None) if step_id is None else BugLink.step_id == step_id,
    )
    return s.execute(stmt.limit(1)).scalar_one_or_none()


def add(s: Session, row: BugLink) -> None:
    s.add(row)
    s.flush()


def remove(s: Session, row: BugLink) -> None:
    s.delete(row)
    s.flush()


def links_of_result(s: Session, ctx: AccessContext, result_id: UUID) -> list[BugLink]:
    return list(
        s.execute(_scope(ctx).where(BugLink.result_id == result_id).order_by(BugLink.created_at)).scalars()
    )


def delete_links_of_result(s: Session, ctx: AccessContext, result_id: UUID) -> None:
    s.execute(
        delete(BugLink).where(
            BugLink.organization_id == ctx.principal.organization_id,
            BugLink.project_id == ctx.pid,
            BugLink.result_id == result_id,
        )
    )


def has_link_on_result(s: Session, ctx: AccessContext, result_id: UUID) -> bool:
    return s.execute(_scope(ctx).where(BugLink.result_id == result_id).limit(1)).first() is not None


def links_of_runs(s: Session, ctx: AccessContext, run_ids: Sequence[UUID]) -> list[BugLink]:
    if not run_ids:
        return []
    stmt = _scope(ctx).where(BugLink.run_id.in_(list(run_ids))).order_by(BugLink.created_at, BugLink.id)
    return list(s.execute(stmt).scalars())


def links_of_case(s: Session, ctx: AccessContext, case_id: UUID) -> list[BugLink]:
    stmt = _scope(ctx).where(BugLink.test_case_id == case_id).order_by(BugLink.created_at.desc(), BugLink.id)
    return list(s.execute(stmt).scalars())


def links_of_reference(s: Session, ctx: AccessContext, reference_norm: str) -> list[BugLink]:
    stmt = (
        _scope(ctx).where(BugLink.reference_norm == reference_norm).order_by(BugLink.created_at, BugLink.id)
    )
    return list(s.execute(stmt).scalars())


def references(
    s: Session, ctx: AccessContext, *, q: str | None, run_ids: Sequence[UUID] | None
) -> list[BugLink]:
    """All links of the project (optionally limited to runs or matching text), for grouping by reference.
    Volumes are small (links, not bugs); grouping happens in queries.py."""
    stmt = _scope(ctx)
    if q:
        text = q.strip().upper()
        stmt = stmt.where(
            BugLink.reference_norm.contains(text, autoescape=True)
            | func.upper(BugLink.title).contains(text, autoescape=True)
        )
    if run_ids is not None:
        stmt = stmt.where(BugLink.run_id.in_(list(run_ids)))
    return list(s.execute(stmt.order_by(BugLink.created_at, BugLink.id)).scalars())


def recent_references(s: Session, ctx: AccessContext, run_ids: Sequence[UUID], limit: int) -> list[BugLink]:
    if not run_ids:
        return []
    stmt = _scope(ctx).where(BugLink.run_id.in_(list(run_ids))).order_by(BugLink.created_at.desc()).limit(200)
    seen: dict[str, BugLink] = {}
    for row in s.execute(stmt).scalars():
        seen.setdefault(row.reference_norm, row)
        if len(seen) >= limit:
            break
    return list(seen.values())


def owner_of(s: Session, link_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(select(BugLink.organization_id, BugLink.project_id).where(BugLink.id == link_id)).first()
    return (row[0], row[1]) if row else None
