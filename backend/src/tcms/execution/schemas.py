"""Cycle and run API schemas (docs/06 §4.6, §5.3, §5.4, §5.7)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcms.core.enums import CycleStatus, RunStatus
from tcms.execution.rules import BUILD_MAX, NAME_MAX, NAME_MIN
from tcms.identity.schemas import UserRef
from tcms.testdesign.schemas import AttachmentRead, VersionRead

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
    """An attempt in a run's history (docs/06 §5.4)."""

    id: UUID
    attempt_no: int
    state: str
    status: str | None
    executed_by: UserRef | None
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: int | None = None
    reason: str | None = None
    comment: str | None = None
    skipped_steps: int
    corrects_result_id: UUID | None
    corrected_by_result_id: UUID | None = Field(
        default=None, description="Set when a later attempt corrects this one (shown struck through)"
    )


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
    draft: ResultRead | None = Field(
        default=None, description="The open attempt with its steps (include=draft)"
    )
    history: list[AttemptRead] | None = None
    queue: QueueRead | None = Field(default=None, description="Runner queue neighbours (include=queue)")
    row_version: int


# -- attempts (M4, docs/06 §4.7, §5.5) -------------------------------------------------------------

StepStatusIn = Literal["not_run", "passed", "failed", "blocked", "skipped"]
Outcome = Literal["passed", "failed", "blocked", "skipped", "not_applicable"]


class StepResultRead(BaseModel):
    id: UUID = Field(description="Step result id (attachments use entity_type=test_step_result)")
    step_id: UUID
    position: int
    status: StepStatusIn
    actual_result: str | None
    comment: str | None
    attachments: list[AttachmentRead]
    updated_at: datetime


class ResultRead(BaseModel):
    id: UUID
    run_id: UUID
    attempt_no: int
    state: Literal["draft", "final"]
    status: Outcome | None
    source: str
    executed_by: UserRef | None
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: int | None
    build: str | None
    environment: Ref
    comment: str | None
    reason: str | None
    skipped_steps: int
    corrects_result_id: UUID | None
    steps: list[StepResultRead]


class StartAttemptRequest(_Model):
    take_over: bool = False
    corrects_result_id: UUID | None = None


class AttemptPatch(_Model):
    comment: str | None = Field(default=None, max_length=20_000)
    build: str | None = Field(default=None, max_length=100)
    duration_seconds: int | None = Field(default=None, ge=0, le=86_400)


class StepPatch(_Model):
    status: StepStatusIn | None = None
    actual_result: str | None = Field(default=None, max_length=20_000)
    comment: str | None = Field(default=None, max_length=20_000)


class BulkStepsRequest(_Model):
    status: Literal["passed"]
    only_not_run: Literal[True]


class FinalizeRequest(_Model):
    outcome: Outcome | None = None
    reason: str | None = Field(default=None, max_length=1000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86_400)


class FinalizeResponse(BaseModel):
    result: ResultRead
    run: RunRead


class QueueRead(BaseModel):
    filter: Literal["mine_open", "mine", "open", "all"]
    position: int | None
    total: int
    previous_run_id: UUID | None
    next_run_id: UUID | None


class ProjectRef(BaseModel):
    id: UUID
    key: str
    name: str


class MyWorkCycle(BaseModel):
    project: ProjectRef
    id: UUID
    key: str
    name: str
    status: CycleStatus
    start_date: date | None
    due_date: date | None
    summary: ExecutionSummaryRead
    next_run_id: UUID | None = Field(description="My first run that is not finished (Start / Continue)")


class MyWorkReview(BaseModel):
    project: ProjectRef
    id: UUID
    key: str
    title: str
    updated_at: datetime


class MyWorkAttention(BaseModel):
    project: ProjectRef
    run_id: UUID
    cycle_id: UUID
    cycle_key: str
    case_key: str
    title: str
    status: RunStatus
    needs_retest: bool


class MyWorkRead(BaseModel):
    """docs/06 §4.1 `GET /me/work` (docs/07 §5.14, docs/02 §11.3 QA Engineer dashboard)."""

    cycles: list[MyWorkCycle]
    reviews: list[MyWorkReview]
    week: ExecutionSummaryRead = Field(description="Attempts I finished in the last 7 days")
    today: ExecutionSummaryRead = Field(description="Attempts I finished today (UTC)")
    attention: list[MyWorkAttention] = Field(description="My failed / blocked runs and runs to retest")
    bugs_linked_week: int = Field(description="Distinct bug references I linked in the last 7 days")


RunRead.model_rebuild()
FinalizeResponse.model_rebuild()
