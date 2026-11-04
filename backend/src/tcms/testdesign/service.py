"""Test design use cases. M1: system tags for new projects (docs/05 §8.2, FR-TD-008)."""

from __future__ import annotations

from tcms.core import clock, ids
from tcms.core.events import subscribe
from tcms.core.uow import UnitOfWork
from tcms.testdesign.models import Tag
from tcms.workspace.service import ProjectCreated

SYSTEM_TAGS = ("smoke", "sanity", "regression")


@subscribe(ProjectCreated)
def create_system_tags(uow: UnitOfWork, event: ProjectCreated) -> None:
    """In-transaction handler (docs/03 §5.4): every project starts with the system tags."""
    now = clock.now()
    for name in SYSTEM_TAGS:
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
