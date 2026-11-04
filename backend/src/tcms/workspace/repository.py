"""Workspace data access (private to the module). Every query is organization/project scoped."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from tcms.core.enums import ProjectStatus
from tcms.workspace.models import Environment, KeySequence, Organization, Project, Release


def organization(s: Session, org_id: UUID, *, for_update: bool = False) -> Organization | None:
    stmt = select(Organization).where(Organization.id == org_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def organization_by_slug(s: Session, slug: str) -> Organization | None:
    return s.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none()


def project(s: Session, org_id: UUID, project_id: UUID, *, for_update: bool = False) -> Project | None:
    stmt = select(Project).where(Project.organization_id == org_id, Project.id == project_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def project_by_key(s: Session, org_id: UUID, key: str) -> Project | None:
    return s.execute(
        select(Project).where(Project.organization_id == org_id, Project.key == key)
    ).scalar_one_or_none()


def active_project_named(
    s: Session, org_id: UUID, name: str, *, exclude: UUID | None = None
) -> Project | None:
    stmt = select(Project).where(
        Project.organization_id == org_id,
        Project.status == ProjectStatus.active,
        func.lower(Project.name) == name.lower(),
    )
    if exclude is not None:
        stmt = stmt.where(Project.id != exclude)
    return s.execute(stmt).scalar_one_or_none()


def projects(
    s: Session, org_id: UUID, *, ids: set[UUID] | None, status: ProjectStatus | None
) -> list[Project]:
    stmt = select(Project).where(Project.organization_id == org_id)
    if ids is not None:
        if not ids:
            return []
        stmt = stmt.where(Project.id.in_(ids))
    if status is not None:
        stmt = stmt.where(Project.status == status)
    return list(s.execute(stmt.order_by(func.lower(Project.name))).scalars().all())


def environments(s: Session, org_id: UUID, project_id: UUID, *, include_archived: bool) -> list[Environment]:
    stmt = select(Environment).where(
        Environment.organization_id == org_id, Environment.project_id == project_id
    )
    if not include_archived:
        stmt = stmt.where(Environment.archived_at.is_(None))
    return list(s.execute(stmt.order_by(func.lower(Environment.name))).scalars().all())


def environment(s: Session, org_id: UUID, env_id: UUID, *, for_update: bool = False) -> Environment | None:
    stmt = select(Environment).where(Environment.organization_id == org_id, Environment.id == env_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def environment_named(
    s: Session, project_id: UUID, name: str, *, exclude: UUID | None = None
) -> Environment | None:
    stmt = select(Environment).where(
        Environment.project_id == project_id, func.lower(Environment.name) == name.lower()
    )
    if exclude is not None:
        stmt = stmt.where(Environment.id != exclude)
    return s.execute(stmt).scalar_one_or_none()


def releases(s: Session, org_id: UUID, project_id: UUID) -> list[Release]:
    return list(
        s.execute(
            select(Release)
            .where(Release.organization_id == org_id, Release.project_id == project_id)
            .order_by(Release.target_date.desc().nulls_last(), func.lower(Release.name))
        )
        .scalars()
        .all()
    )


def release(s: Session, org_id: UUID, release_id: UUID, *, for_update: bool = False) -> Release | None:
    stmt = select(Release).where(Release.organization_id == org_id, Release.id == release_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def release_named(s: Session, project_id: UUID, name: str, *, exclude: UUID | None = None) -> Release | None:
    stmt = select(Release).where(Release.project_id == project_id, func.lower(Release.name) == name.lower())
    if exclude is not None:
        stmt = stmt.where(Release.id != exclude)
    return s.execute(stmt).scalar_one_or_none()


def next_key_number(s: Session, project_id: UUID, entity: str) -> int:
    """docs/04 §3.6: never reused; serialized by the row lock taken by UPDATE."""
    result = s.execute(
        update(KeySequence)
        .where(KeySequence.project_id == project_id, KeySequence.entity == entity)
        .values(next_value=KeySequence.next_value + 1)
        .returning(KeySequence.next_value - 1)
    ).scalar_one()
    return int(result)


def project_of_environment(s: Session, env_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(Environment.organization_id, Environment.project_id).where(Environment.id == env_id)
    ).first()
    return (row[0], row[1]) if row else None


def project_of_release(s: Session, release_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(Release.organization_id, Release.project_id).where(Release.id == release_id)
    ).first()
    return (row[0], row[1]) if row else None
