"""Workspace request/response models (docs/06 §4.2, §4.3)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcms.core.enums import ProjectStatus, ReleaseStatus


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrgSettings(BaseModel):
    mfa_required_for_all: bool
    session_idle_minutes: int
    session_absolute_hours: int
    qa_managers_can_create_projects: bool
    default_attachment_max_mb: int
    audit_retention_years: int


class OrgSettingsPatch(_Model):
    mfa_required_for_all: bool | None = None
    session_idle_minutes: int | None = None
    session_absolute_hours: int | None = None
    qa_managers_can_create_projects: bool | None = None
    default_attachment_max_mb: int | None = None
    audit_retention_years: int | None = None


class OrganizationRead(BaseModel):
    id: UUID
    name: str
    slug: str
    settings: OrgSettings | None = Field(description="Present for Org Admins")
    row_version: int


class OrganizationPatch(_Model):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    settings: OrgSettingsPatch | None = None
    row_version: int | None = None


class ProjectSettings(BaseModel):
    approval_required: bool
    allow_self_approval: bool
    only_assignee_executes: bool
    report_module_depth: int
    attachment_max_mb: int
    require_defect_for_failure: bool


class ProjectSettingsPatch(_Model):
    approval_required: bool | None = None
    allow_self_approval: bool | None = None
    only_assignee_executes: bool | None = None
    report_module_depth: int | None = None
    attachment_max_mb: int | None = None
    require_defect_for_failure: bool | None = None


class ProjectCounts(BaseModel):
    members: int
    environments: int
    releases: int


class ProjectRead(BaseModel):
    id: UUID
    key: str
    name: str
    description: str | None
    status: ProjectStatus
    settings: ProjectSettings
    counts: ProjectCounts | None = None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class ProjectCreate(_Model):
    key: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=20000)


class ProjectPatch(_Model):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=20000)
    settings: ProjectSettingsPatch | None = None
    row_version: int | None = None


class ArchiveRequest(_Model):
    confirm_key: str = Field(min_length=1, max_length=20)
    close_open_cycles: bool = Field(
        default=False,
        description="Close planned/active cycles first (docs/02 §4.2); otherwise 409 lists them",
    )


class EnvironmentRead(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    description: str | None
    archived: bool
    archived_at: datetime | None
    row_version: int


class EnvironmentCreate(_Model):
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=20000)


class EnvironmentPatch(_Model):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=20000)
    row_version: int | None = None


class ReleaseRead(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    description: str | None
    status: ReleaseStatus
    start_date: date | None
    target_date: date | None
    released_at: datetime | None
    allowed_transitions: list[ReleaseStatus]
    row_version: int


class ReleaseCreate(_Model):
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=20000)
    start_date: date | None = None
    target_date: date | None = None


class ReleasePatch(_Model):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=20000)
    start_date: date | None = None
    target_date: date | None = None
    status: ReleaseStatus | None = None
    row_version: int | None = None


class ActivityItem(BaseModel):
    id: UUID
    occurred_at: datetime
    actor_type: str
    actor_id: UUID | None
    actor_display: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    entity_key: str | None
    changes: dict[str, Any] | None
    summary: str | None


class EnumValues(BaseModel):
    values: list[str]


MetaEnums = dict[str, list[str]]


class PermissionRead(BaseModel):
    permission: str
    scope: Literal["org", "project"]
