"""Administration API models (docs/06 §4.2, §4.12; M8b)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AuditEventRead(BaseModel):
    id: UUID
    occurred_at: datetime
    project_id: UUID | None
    project_key: str | None = None
    actor_type: str
    actor_id: UUID | None
    actor_display: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    entity_key: str | None
    changes: dict[str, Any] | None = Field(description="{field: [old, new]}")
    summary: str | None
    context: dict[str, Any] = Field(description="request_id, ip, user_agent, bulk_operation_id and extras")


class AccessReviewRow(BaseModel):
    user_id: UUID
    email: str
    name: str
    active: bool
    org_admin: bool
    mfa_enrolled: bool
    project_id: UUID | None = Field(description="None: the organization row")
    project_key: str | None
    project_name: str | None
    role_code: str = Field(description="org_admin, org_member or a project role code")
    role_name: str
    granted_by: str | None
    granted_at: datetime | None
    last_sign_in: datetime | None


class CheckRead(BaseModel):
    ok: bool
    detail: str | None = None


class JobStatsRead(BaseModel):
    counts: dict[str, int] = Field(description="queued, running, succeeded, failed, dead")
    oldest_due_at: datetime | None = Field(description="Longest-waiting queued job that is due")
    last_succeeded_at: datetime | None


class StorageUsage(BaseModel):
    files: int
    bytes: int


class SystemStatus(BaseModel):
    version: str
    environment: str
    migration_current: str | None
    migration_head: str | None
    checks: dict[str, CheckRead]
    jobs: JobStatsRead
    attachments: StorageUsage
    audit_retention_years: int
    checked_at: datetime


class JobRead(BaseModel):
    id: UUID
    type: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    run_at: datetime
    created_at: datetime
    finished_at: datetime | None
    system: bool = Field(description="An installation job, not tied to one organization")
