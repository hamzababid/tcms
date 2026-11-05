"""Cycle and run API schemas (docs/06 §4.6)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcms.core.enums import CycleStatus, RunStatus
from tcms.execution.rules import BUILD_MAX, NAME_MAX, NAME_MIN
from tcms.identity.schemas import UserRef


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelectionIn(_Model):
    from_plan: bool = False
    case_ids: list[UUID] = Field(default_factory=list)
    folder_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)


class CycleCreate(_Model):
    name: str = Field(min_length=NAME_MIN, max_length=NAME_MAX)
    environment_id: UUID
    release_id: UUID | None = None
    plan_id: UUID | None = None
    build: str | None = Field(default=None, max_length=BUILD_MAX)
    start_date: date | None = None
    due_date: date | None = None
    description: str | None = Field(default=None, max_length=20000)
    selection: SelectionIn = Field(default_factory=SelectionIn)
    default_assignee_id: UUID | None = None


class CyclePatch(_Model):
    name: str | None = Field(default=None, min_length=NAME_MIN, max_length=NAME_MAX)
    description: str | None = Field(default=None, max_length=20000)
    build: str | None = Field(default=None, max_length=BUILD_MAX)
    start_date: date | None = None
    due_date: date | None = None
    environment_id: UUID | None = None
    row_version: int | None = None


class AddCasesRequest(_Model):
    case_ids: list[UUID] = Field(default_factory=list)
    folder_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RunIdsRequest(_Model):
    run_ids: list[UUID] = Field(min_length=1)


class AssignRequest(_Model):
    run_ids: list[UUID] = Field(min_length=1)
    assignee_id: UUID | None = None  # null = unassign


class CloseRequest(_Model):
    discard_drafts: bool = False


class ReopenRequest(_Model):
    reason: str = Field(min_length=1, max_length=2000)


class CloneRequest(_Model):
    name: str = Field(min_length=NAME_MIN, max_length=NAME_MAX)
    only_statuses: list[RunStatus] | None = None


class ReorderRequest(_Model):
    ordered_run_ids: list[UUID] | None = None
    sort_by: str | None = Field(default=None, pattern="^(folder|priority)$")


class Skipped(BaseModel):
    key: str
    reason: str


class CountResponse(BaseModel):
    count: int


class CycleSummary(BaseModel):
    """Counts by run status over non-superseded runs."""

    total: int
    by_status: dict[str, int]


class CycleCreateResponse(BaseModel):
    cycle_id: UUID
    key: str
    added: int
    skipped: list[Skipped]
    runs_pending: bool


class AddRunsResponse(BaseModel):
    added: int
    skipped: list[Skipped]


class AssigneeProgress(BaseModel):
    assignee: UserRef | None
    by_status: dict[str, int]
    total: int


class CycleRead(BaseModel):
    id: UUID
    key: str
    project_id: UUID
    name: str
    description: str | None
    release_id: UUID | None
    plan_id: UUID | None
    environment_id: UUID
    build: str | None
    status: CycleStatus
    start_date: date | None
    due_date: date | None
    owner: UserRef | None
    runs_pending: bool
    summary: CycleSummary
    progress_by_assignee: list[AssigneeProgress]
    archived: bool
    created_at: datetime
    updated_at: datetime
    row_version: int


class CycleListItem(BaseModel):
    id: UUID
    key: str
    name: str
    status: CycleStatus
    release_id: UUID | None
    plan_id: UUID | None
    environment_id: UUID
    due_date: date | None
    summary: CycleSummary
    updated_at: datetime
    row_version: int


class RunRead(BaseModel):
    id: UUID
    cycle_id: UUID
    test_case_id: UUID
    case_key: str
    title: str
    version_no: int
    latest_version_no: int
    position: int
    assignee: UserRef | None
    status: RunStatus
    needs_retest: bool
    superseded: bool
    row_version: int
