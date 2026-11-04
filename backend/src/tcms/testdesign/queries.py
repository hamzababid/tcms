"""Public read functions of the testdesign module."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcms.testdesign.models import Tag


def tag_names(s: Session, org_id: UUID, project_id: UUID) -> list[tuple[str, bool]]:
    rows = s.execute(
        select(Tag.name, Tag.is_system)
        .where(Tag.organization_id == org_id, Tag.project_id == project_id)
        .order_by(Tag.name)
    ).all()
    return [(n, bool(sys)) for n, sys in rows]
