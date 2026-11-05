"""Public read functions of the requirements module.

The full module arrives in M6; for now this exposes only the minimal scoped lookups that planning
needs to validate requirement links (US-072 / FR-PLN-003).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.requirements.models import Requirement


def existing_ids(s: Session, ctx: AccessContext, ids: list[UUID]) -> set[UUID]:
    """The subset of `ids` that are requirements in the context project (scoped)."""
    if not ids:
        return set()
    stmt = select(Requirement.id).where(
        Requirement.organization_id == ctx.principal.organization_id,
        Requirement.project_id == ctx.pid,
        Requirement.id.in_(ids),
    )
    return set(s.execute(stmt).scalars())
