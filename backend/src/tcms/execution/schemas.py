"""Cycle and run API schemas (docs/06 §4.6, §5.3, §5.4, §5.7)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcms.core.enums import CycleStatus, RunStatus
from tcms.execution.rules import BUILD_MAX, NAME_MAX, NAME_MIN
from tcms.identity.schemas import UserRef
from tcms.testdesign.schemas import VersionRead

CloneStatus = Literal["failed", "blocked", "not_run"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# -- requests -------------------------------------------------------------------------------------


class SelectionIn(_Model):
    from_plan: bool = False
    case_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    folder_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    priorities: list[Literal["critical", "high", "medium", "low"]] = Field(default_factory=list)


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
    release_id: UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    environment_id: UUID | None = None
    row_version: int | None = None


class AddCasesRequest(_Model):
    case_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    folder_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RunIdsRequest(_Model):
    run_ids: list[UUID] = Field(min_length=1, max_length=5000)


class AssignRequest(_Model):
    """docs/06 §4.6: `{run_ids? | filter?, assignee_id | null}`; `filter` takes the runs-list filters."""

    run_ids: list[UUID] | None = Field(default=None, max_length=5000)
    filter: dict[str, str] | None = None
    assignee_id: UUID | None = None


class CloseRequest(_Model):
    discard_drafts: bool = False


class ReopenRequest(_Model):
    reason: str = Field(max_length=2000)


class CloneRequest(_Model):
    name: str = Field(min_length=NAME_MIN, max_length=NAME_MAX)
    only_statuses: list[CloneStatus] | None = None


class ReorderRequest(_Model):
    """docs/06 §4.6: `{run_ids_in_order}` or `{sort_by: folder|priority}`."""

    run_ids_in_order: list[UUID] | None = None
    sort_by: Literal["folder", "priority"] | None = None


# -- shared read models ---------------------------------------------------------------------------


class Ref(BaseModel):
    id: UUID
    name: str


class KeyRef(BaseModel):
    id: UUID
    key: str
    title: str


class RateRead(BaseModel):
    numerator: int
    denominator: int
    value: float | None


class ExecutionSummaryRead(BaseModel):
    """docs/06 §5.7; rates are null when the denominator is 0 (BR-24)."""

    total: int
    not_applicable: int
    applicable: int
    passed: int
    failed: int
    blocked: int
    skipped: int
    in_progress: int
    not_run: int
    executed: int
    execution_progress: RateRead
    pass_rate: RateRead
    pass_rate_applicable: RateRead
    failure_rate: RateRead
    blocked_rate: RateRead
    needs_retest: int


class GroupProgress(BaseModel):
    id: UUID | None = Field(description="Assignee or folder id; null = unassigned")
    name: str
    summary: ExecutionSummaryRead


class Skipped(BaseModel):
    key: str
    reason: str


class CountResponse(BaseModel):
    count: int


class AddRunsResponse(BaseModel):
    added: int
    skipped: list[Skipped]


# -- cycles ---------------------------------------------------------------------------------------


class CycleRead(BaseModel):
    """docs/06 §5.3 plus progress by assignee and folder (FR-EXE-013)."""

    id: UUID
    key: str
    project_id: UUID
    name: str
    description: str | None
    status: CycleStatus
    release: Ref | None
    plan: KeyRef | None
    environment: Ref
    build: str | None
    start_date: date | None
    due_date: date | None
    owner: UserRef | None
    runs_pending: bool
    summary: ExecutionSummaryRead
    superseded_runs: int
    progress_by_assignee: list[GroupProgress]
    progress_by_folder: list[GroupProgress]
    started_at: datetime | None
    closed_at: datetime | None
    closed_by: UserRef | None
    archived: bool
    created_at: datetime
    updated_at: datetime
    row_version: int


class CycleListItem(BaseModel):
    id: UUID
    key: str
    name: str
    status: CycleStatus
    release: Ref | None
    plan: KeyRef | None
    environment: Ref
    build: str | None
    start_date: date | None
    due_date: date | None
    owner: UserRef | None
    runs_pending: bool
    summary: ExecutionSummaryRead
    archived: bool
    updated_at: datetime
    row_version: int


class CycleCreateResponse(BaseModel):
    """docs/06 §4.6: `201 {cycle, added, skipped[]}`, or `202` while runs are created in the background."""

    cycle: CycleRead
    added: int
    skipped: list[Skipped]
    runs_pending: bool


# -- runs -----------------------------------------------------------------------------------------


class RunCase(BaseModel):
    id: UUID
    key: str
    title: str
    priority: str
    folder_id: UUID
    folder_name: str


class RunListItem(BaseModel):
    id: UUID
    cycle_id: UUID
    position: int
    test_case: RunCase
    pinned_version_no: int
    newer_version_no: int | None = Field(description="Set when a newer eligible version exists ('v3↑')")
    assignee: UserRef | None
    status: RunStatus
    needs_retest: bool
    superseded: bool
    updated_at: datetime
    row_version: int


class NewerVersionRead(BaseModel):
    version_no: int
    eligible: bool
    can_update: bool
    reason: str | None


class AttemptRead(BaseModel):
    id: UUID
    attempt_no: int
    state: str
    status: str | None
    executed_by: UserRef | None
    started_at: datetime
    finished_at: datetime | None
    skipped_steps: int
    corrects_result_id: UUID | None


class RunCycleRef(BaseModel):
    id: UUID
    key: str
    name: str
    status: CycleStatus


class RunCaseDetail(RunCase):
    folder_path: list[str]


class RunRead(BaseModel):
    """docs/06 §5.4. `version`, `draft` and `history` are filled when requested with `include=`; linked
    defects arrive with M5."""

    id: UUID
    cycle: RunCycleRef
    position: int
    test_case: RunCaseDetail
    pinned_version_no: int
    newer_version: NewerVersionRead | None
    assignee: UserRef | None
    status: RunStatus
    needs_retest: bool
    superseded_by_run_id: UUID | None
    has_attempts: bool
    version: VersionRead | None = Field(default=None, description="The pinned version (include=version)")
    draft: AttemptRead | None = None
    history: list[AttemptRead] | None = None
    row_version: int
