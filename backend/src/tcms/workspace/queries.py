"""Public read functions of the workspace module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from tcms.core.enums import ProjectStatus
from tcms.core.policy import OrgPolicy
from tcms.workspace import repository as repo
from tcms.workspace import rules
from tcms.workspace.models import Environment, Organization, Project, Release, ReleaseDecision


def org_policy(s: Session, org_id: UUID) -> OrgPolicy:
    org = repo.organization(s, org_id)
    return OrgPolicy.from_settings(org.settings if org else None)


def organization(s: Session, org_id: UUID) -> Organization | None:
    return repo.organization(s, org_id)


def organization_by_slug(s: Session, slug: str) -> Organization | None:
    return repo.organization_by_slug(s, slug)


def org_settings(org: Organization) -> dict[str, Any]:
    return rules.merged_org_settings(org.settings, {})


@dataclass(frozen=True)
class ProjectRef:
    id: UUID
    organization_id: UUID
    key: str
    name: str
    status: ProjectStatus


def project_ref(s: Session, org_id: UUID, project_id: UUID) -> ProjectRef | None:
    p = repo.project(s, org_id, project_id)
    return ProjectRef(p.id, p.organization_id, p.key, p.name, p.status) if p else None


def project(s: Session, org_id: UUID, project_id: UUID) -> Project | None:
    return repo.project(s, org_id, project_id)


def projects(
    s: Session, org_id: UUID, *, ids: set[UUID] | None, status: ProjectStatus | None
) -> list[Project]:
    return repo.projects(s, org_id, ids=ids, status=status)


def project_settings(p: Project) -> dict[str, Any]:
    return rules.merged_project_settings(p.settings, {})


def project_settings_of(s: Session, org_id: UUID, project_id: UUID) -> dict[str, Any]:
    p = repo.project(s, org_id, project_id)
    return rules.merged_project_settings(p.settings if p else {}, {})


def environments(s: Session, org_id: UUID, project_id: UUID, *, include_archived: bool) -> list[Environment]:
    return repo.environments(s, org_id, project_id, include_archived=include_archived)


def releases(s: Session, org_id: UUID, project_id: UUID) -> list[Release]:
    return repo.releases(s, org_id, project_id)


def release(s: Session, org_id: UUID, release_id: UUID) -> Release | None:
    return repo.release(s, org_id, release_id)


def decisions(s: Session, org_id: UUID, release_id: UUID) -> list[ReleaseDecision]:
    return repo.decisions(s, org_id, [release_id])


def latest_decisions(s: Session, org_id: UUID, release_ids: list[UUID]) -> dict[UUID, ReleaseDecision]:
    out: dict[UUID, ReleaseDecision] = {}
    for d in repo.decisions(s, org_id, release_ids):
        out.setdefault(d.release_id, d)
    return out


def allowed_release_targets(r: Release) -> list[str]:
    return sorted(t.value for t in rules.allowed_release_targets(r.status))


def owning_project(s: Session, entity_type: str, entity_id: UUID) -> tuple[UUID, UUID] | None:
    """(organization_id, project_id) of a workspace entity addressed by ID (docs/04 §3.3)."""
    if entity_type == "environment":
        return repo.project_of_environment(s, entity_id)
    if entity_type == "release":
        return repo.project_of_release(s, entity_id)
    raise ValueError(f"workspace does not own {entity_type}")
