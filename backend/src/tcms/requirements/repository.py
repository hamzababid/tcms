"""Requirement-reference data access (private to the module). Every query is project-scoped."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.requirements.models import RequirementRef, RequirementRefCase


def _scope(ctx: AccessContext) -> Any:
    return select(RequirementRef).where(
        RequirementRef.organization_id == ctx.principal.organization_id, RequirementRef.project_id == ctx.pid
    )


def ref(s: Session, ctx: AccessContext, ref_id: UUID, *, for_update: bool = False) -> RequirementRef | None:
    stmt = _scope(ctx).where(RequirementRef.id == ref_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def refs_by_norm(s: Session, ctx: AccessContext, norms: Sequence[str]) -> dict[str, RequirementRef]:
    if not norms:
        return {}
    rows = s.execute(_scope(ctx).where(RequirementRef.reference_norm.in_(list(norms)))).scalars()
    return {r.reference_norm: r for r in rows}


def refs_by_ids(s: Session, ctx: AccessContext, ids: Sequence[UUID]) -> list[RequirementRef]:
    if not ids:
        return []
    return list(s.execute(_scope(ctx).where(RequirementRef.id.in_(list(ids)))).scalars())


def add(s: Session, row: RequirementRef) -> None:
    s.add(row)
    s.flush()


def list_stmt(ctx: AccessContext, *, include_archived: bool) -> Any:
    stmt = _scope(ctx)
    if not include_archived:
        stmt = stmt.where(RequirementRef.archived_at.is_(None))
    return stmt


def case_ids_of(s: Session, ref_id: UUID) -> list[UUID]:
    return list(
        s.execute(
            select(RequirementRefCase.test_case_id).where(RequirementRefCase.ref_id == ref_id)
        ).scalars()
    )


def case_counts(s: Session, ref_ids: Sequence[UUID]) -> dict[UUID, int]:
    if not ref_ids:
        return {}
    rows = s.execute(
        select(RequirementRefCase.ref_id, func.count())
        .where(RequirementRefCase.ref_id.in_(list(ref_ids)))
        .group_by(RequirementRefCase.ref_id)
    ).all()
    return {r[0]: int(r[1]) for r in rows}


def linked_ref_ids(s: Session, ctx: AccessContext) -> Any:
    """Subquery of references with at least one linked case."""
    return select(RequirementRefCase.ref_id).where(RequirementRefCase.project_id == ctx.pid)


def refs_of_case(s: Session, ctx: AccessContext, case_id: UUID) -> list[RequirementRef]:
    stmt = (
        _scope(ctx)
        .join(RequirementRefCase, RequirementRefCase.ref_id == RequirementRef.id)
        .where(RequirementRefCase.test_case_id == case_id)
    )
    return list(s.execute(stmt).scalars())


def existing_links(s: Session, ref_ids: Sequence[UUID], case_ids: Sequence[UUID]) -> set[tuple[UUID, UUID]]:
    if not ref_ids or not case_ids:
        return set()
    rows = s.execute(
        select(RequirementRefCase.ref_id, RequirementRefCase.test_case_id).where(
            RequirementRefCase.ref_id.in_(list(ref_ids)), RequirementRefCase.test_case_id.in_(list(case_ids))
        )
    ).all()
    return {(r[0], r[1]) for r in rows}


def add_link(s: Session, ctx: AccessContext, ref_id: UUID, case_id: UUID, actor: UUID | None) -> None:
    s.add(
        RequirementRefCase(
            ref_id=ref_id,
            test_case_id=case_id,
            organization_id=ctx.principal.organization_id,
            project_id=ctx.pid,
            created_by=actor,
        )
    )


def remove_link(s: Session, ctx: AccessContext, ref_id: UUID, case_id: UUID) -> int:
    res = s.execute(
        delete(RequirementRefCase).where(
            RequirementRefCase.project_id == ctx.pid,
            RequirementRefCase.ref_id == ref_id,
            RequirementRefCase.test_case_id == case_id,
        )
    )
    return int(getattr(res, "rowcount", 0) or 0)


def search(s: Session, ctx: AccessContext, q: str, limit: int) -> list[RequirementRef]:
    text = q.strip().upper()
    stmt = (
        list_stmt(ctx, include_archived=False)
        .where(
            RequirementRef.reference_norm.contains(text, autoescape=True)
            | func.upper(RequirementRef.title).contains(text, autoescape=True)
        )
        .order_by((RequirementRef.reference_norm == text).desc(), RequirementRef.reference_norm)
        .limit(limit)
    )
    return list(s.execute(stmt).scalars())


def owner_of(s: Session, ref_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(RequirementRef.organization_id, RequirementRef.project_id).where(RequirementRef.id == ref_id)
    ).first()
    return (row[0], row[1]) if row else None


def links_of_refs(s: Session, ctx: AccessContext, ref_ids: Sequence[UUID]) -> list[tuple[UUID, UUID]]:
    if not ref_ids:
        return []
    rows = s.execute(
        select(RequirementRefCase.ref_id, RequirementRefCase.test_case_id).where(
            RequirementRefCase.project_id == ctx.pid, RequirementRefCase.ref_id.in_(list(ref_ids))
        )
    ).all()
    return [(r[0], r[1]) for r in rows]
