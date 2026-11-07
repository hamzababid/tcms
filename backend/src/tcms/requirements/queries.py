"""Public read functions of the requirements module (docs/02 §10; ADR-024).

Requirement references: the team's identifiers for requirements kept in its own tool. Coverage per release
is computed in `reporting.coverage`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.core.errors import NotFound
from tcms.core.references import natural_key, reference_norm
from tcms.requirements import repository as repo
from tcms.requirements.models import Requirement, RequirementRef


def existing_ids(s: Session, ctx: AccessContext, ids: list[UUID]) -> set[UUID]:
    """Baseline requirement rows (unused since ADR-024); kept for the old plan link contract."""
    if not ids:
        return set()
    stmt = select(Requirement.id).where(
        Requirement.organization_id == ctx.principal.organization_id,
        Requirement.project_id == ctx.pid,
        Requirement.id.in_(ids),
    )
    return set(s.execute(stmt).scalars())


@dataclass(frozen=True)
class RefView:
    id: UUID
    reference: str
    url: str | None
    title: str | None
    archived: bool
    case_count: int
    created_at: datetime
    updated_at: datetime
    row_version: int


def _views(s: Session, rows: list[RequirementRef]) -> list[RefView]:
    counts = repo.case_counts(s, [r.id for r in rows])
    return [
        RefView(
            r.id,
            r.reference,
            r.url,
            r.title,
            r.archived_at is not None,
            counts.get(r.id, 0),
            r.created_at,
            r.updated_at,
            r.row_version,
        )
        for r in rows
    ]


def list_refs(
    s: Session,
    ctx: AccessContext,
    *,
    q: str | None,
    linked: bool | None,
    ref_ids: list[UUID] | None,
    include_archived: bool,
) -> list[RefView]:
    """All references of the project, natural order (SPK-2 before SPK-10). `ref_ids` limits to a set (plan
    or release scope); `linked` filters on having linked cases."""
    stmt = repo.list_stmt(ctx, include_archived=include_archived)
    if q and q.strip():
        text = q.strip().upper()
        from sqlalchemy import func

        stmt = stmt.where(
            RequirementRef.reference_norm.contains(text, autoescape=True)
            | func.upper(RequirementRef.title).contains(text, autoescape=True)
        )
    if ref_ids is not None:
        stmt = stmt.where(RequirementRef.id.in_(ref_ids))
    if linked is not None:
        sub = repo.linked_ref_ids(s, ctx)
        stmt = stmt.where(RequirementRef.id.in_(sub) if linked else RequirementRef.id.not_in(sub))
    rows = list(s.execute(stmt).scalars())
    return sorted(_views(s, rows), key=lambda v: natural_key(v.reference))


def ref_detail(s: Session, ctx: AccessContext, ref_id: UUID) -> RefView:
    row = repo.ref(s, ctx, ref_id)
    if row is None:
        raise NotFound()
    return _views(s, [row])[0]


def refs_by_ids(s: Session, ctx: AccessContext, ids: list[UUID]) -> list[RefView]:
    return sorted(_views(s, repo.refs_by_ids(s, ctx, ids)), key=lambda v: natural_key(v.reference))


def ref_by_reference(s: Session, ctx: AccessContext, reference: str) -> RefView | None:
    row = repo.refs_by_norm(s, ctx, [reference_norm(reference)]).get(reference_norm(reference))
    return _views(s, [row])[0] if row else None


def refs_of_case(s: Session, ctx: AccessContext, case_id: UUID) -> list[RefView]:
    return sorted(_views(s, repo.refs_of_case(s, ctx, case_id)), key=lambda v: natural_key(v.reference))


def case_ids_of(s: Session, ctx: AccessContext, ref_id: UUID) -> list[UUID]:
    if repo.ref(s, ctx, ref_id) is None:
        raise NotFound()
    return repo.case_ids_of(s, ref_id)


def case_ids_with_reference(s: Session, ctx: AccessContext, reference: str) -> list[UUID]:
    """Repository filter `requirement` (L19)."""
    view = ref_by_reference(s, ctx, reference)
    return repo.case_ids_of(s, view.id) if view else []


def linked_case_ids_stmt(ctx: AccessContext) -> object:
    """Repository filter `has_requirements` (L19): case ids with at least one reference."""
    from tcms.requirements.models import RequirementRefCase

    return select(RequirementRefCase.test_case_id).where(RequirementRefCase.project_id == ctx.pid)


def search(s: Session, ctx: AccessContext, q: str, limit: int) -> list[RefView]:
    return _views(s, repo.search(s, ctx, q, limit))


def owning_project_of_ref(s: Session, ref_id: UUID) -> tuple[UUID, UUID] | None:
    return repo.owner_of(s, ref_id)


def linked_case_ids(s: Session, ctx: AccessContext, ref_ids: list[UUID]) -> dict[UUID, set[UUID]]:
    """Reference → its linked cases (M8 import/export)."""
    out: dict[UUID, set[UUID]] = {r: set() for r in ref_ids}
    for ref_id, case_id in repo.links_of_refs(s, ctx, ref_ids):
        out.setdefault(ref_id, set()).add(case_id)
    return out
