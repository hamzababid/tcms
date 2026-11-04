"""Test design request/response models (docs/06 §4.4, §5.1, §5.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcms.core.enums import (
    AutomationStatus,
    CaseFormat,
    CaseLinkType,
    CaseStatus,
    CaseType,
    DesignTechnique,
    PriorityLevel,
)
from tcms.identity.schemas import UserRef


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# -- folders --------------------------------------------------------------------------------------


class FolderRead(BaseModel):
    id: UUID
    parent_id: UUID | None
    name: str
    description: str | None
    position: int
    depth: int
    case_count: int = Field(description="Non-archived cases directly in the folder")
    total_count: int = Field(description="Non-archived cases including all subfolders")
    archived: bool
    row_version: int


class FolderCreate(_Model):
    name: str = Field(min_length=1, max_length=120)
    parent_id: UUID | None = None
    description: str | None = Field(default=None, max_length=20000)


class FolderPatch(_Model):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=20000)
    row_version: int | None = None


class FolderMove(_Model):
    parent_id: UUID | None
    position: int | None = Field(default=None, ge=1)
    row_version: int | None = None


# -- content --------------------------------------------------------------------------------------


class StepIn(_Model):
    action: str = Field(max_length=5000)
    expected_result: str | None = Field(default=None, max_length=5000)
    data: str | None = Field(default=None, max_length=2000)


class ContentIn(_Model):
    format: CaseFormat = CaseFormat.steps
    title: str = Field(max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    preconditions: str | None = Field(default=None, max_length=20000)
    test_data: str | None = Field(default=None, max_length=20000)
    expected_result: str | None = Field(default=None, max_length=20000)
    postconditions: str | None = Field(default=None, max_length=20000)
    text_body: str | None = Field(default=None, max_length=20000)
    steps: list[StepIn] = Field(default_factory=list, max_length=100)


class CaseCreate(_Model):
    folder_id: UUID
    type: CaseType = CaseType.functional
    design_technique: DesignTechnique | None = None
    priority: PriorityLevel = PriorityLevel.medium
    tags: list[str] = Field(default_factory=list, max_length=20)
    owner_id: UUID | None = None
    reviewer_id: UUID | None = None
    automation_status: AutomationStatus = AutomationStatus.manual
    automation_keys: list[str] = Field(default_factory=list, max_length=50)
    estimated_minutes: int | None = Field(default=None, ge=0, le=1440)
    content: ContentIn


class ContentUpdate(_Model):
    content: ContentIn
    change_note: str | None = Field(default=None, max_length=500)
    row_version: int | None = None


class CasePatch(_Model):
    """Metadata only: not versioned, audited (BR-01)."""

    folder_id: UUID | None = None
    type: CaseType | None = None
    design_technique: DesignTechnique | None = None
    priority: PriorityLevel | None = None
    owner_id: UUID | None = None
    reviewer_id: UUID | None = None
    automation_status: AutomationStatus | None = None
    estimated_minutes: int | None = Field(default=None, ge=0, le=1440)
    tags: list[str] | None = Field(default=None, max_length=20)
    automation_keys: list[str] | None = Field(default=None, max_length=50)
    row_version: int | None = None


# -- reads ----------------------------------------------------------------------------------------


class AttachmentRead(BaseModel):
    id: UUID
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_by: UserRef | None
    uploaded_at: datetime
    entity_type: str
    entity_id: UUID
    url: str


class StepRead(BaseModel):
    id: UUID
    position: int
    action: str
    expected_result: str | None
    data: str | None
    attachments: list[AttachmentRead] = []


class Approval(BaseModel):
    mode: Literal["auto", "manual"]
    approved_by: UserRef | None
    approved_at: datetime


class Submission(BaseModel):
    submitted_by: UserRef | None
    submitted_at: datetime


class VersionRead(BaseModel):
    id: UUID
    version_no: int
    format: CaseFormat
    title: str
    description: str | None
    preconditions: str | None
    test_data: str | None
    expected_result: str | None
    postconditions: str | None
    text_body: str | None
    change_note: str | None
    created_by: UserRef | None
    created_at: datetime
    submission: Submission | None
    approval: Approval | None
    steps: list[StepRead]


class FolderRef(BaseModel):
    id: UUID
    name: str
    path_names: list[str]


class CaseLinkRead(BaseModel):
    case_id: UUID
    key: str
    title: str
    status: CaseStatus
    link_type: CaseLinkType
    direction: Literal["related", "duplicated_from", "duplicated_to"]


class CaseCounts(BaseModel):
    attachments: int
    comments: int
    versions: int


class CaseRead(BaseModel):
    id: UUID
    key: str
    project_id: UUID
    folder: FolderRef
    title: str
    type: CaseType
    design_technique: DesignTechnique | None
    priority: PriorityLevel
    status: CaseStatus
    format: CaseFormat
    owner: UserRef | None
    reviewer: UserRef | None
    automation_status: AutomationStatus
    automation_keys: list[str]
    estimated_minutes: int | None
    tags: list[str]
    latest_version_no: int
    approved_version_no: int | None
    version: VersionRead
    links: list[CaseLinkRead]
    attachments: list[AttachmentRead]
    counts: CaseCounts
    warnings: list[str] = Field(
        default_factory=list, description="e.g. title_exists (same title in this folder)"
    )
    created_by: UserRef | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class SaveResponse(BaseModel):
    case: CaseRead
    version_created: bool


class CaseListItem(BaseModel):
    id: UUID
    key: str
    title: str
    folder_id: UUID
    type: CaseType
    priority: PriorityLevel
    status: CaseStatus
    format: CaseFormat
    owner: UserRef | None
    automation_status: AutomationStatus
    latest_version_no: int
    approved_version_no: int | None
    tags: list[str]
    updated_at: datetime
    row_version: int


class VersionListItem(BaseModel):
    version_no: int
    title: str
    change_note: str | None
    created_by: UserRef | None
    created_at: datetime
    approval: Approval | None
    submission: Submission | None
    is_latest: bool
    is_approved_version: bool


class FieldDiffRead(BaseModel):
    field: str
    before: str | None
    after: str | None
    changed: bool


class StepContentRead(BaseModel):
    action: str
    expected_result: str | None
    data: str | None


class StepDiffRead(BaseModel):
    position: int
    change: Literal["unchanged", "changed", "added", "removed"]
    before: StepContentRead | None
    after: StepContentRead | None


class CompareRead(BaseModel):
    from_version: int
    to_version: int
    fields: list[FieldDiffRead]
    steps: list[StepDiffRead]


class ExecutionRead(BaseModel):
    run_id: UUID
    cycle_id: UUID
    cycle_key: str
    cycle_name: str
    cycle_status: str
    version_no: int
    status: str
    superseded: bool
    executed_by: UserRef | None
    finished_at: datetime | None


# -- actions --------------------------------------------------------------------------------------


class RestoreVersionRequest(_Model):
    version_no: int = Field(ge=1)
    row_version: int | None = None


class SubmitRequest(_Model):
    reviewer_id: UUID | None = None
    comment: str | None = Field(default=None, max_length=10000)


class ApproveRequest(_Model):
    comment: str | None = Field(default=None, max_length=10000)
    row_version: int | None = None


class ReturnRequest(_Model):
    comment: str = Field(min_length=1, max_length=10000)


class LifecycleRequest(_Model):
    reason: str | None = Field(default=None, max_length=1000)


class DuplicateRequest(_Model):
    folder_id: UUID | None = None
    title: str | None = Field(default=None, min_length=3, max_length=255)


class LinkRequest(_Model):
    target_case_id: UUID
    link_type: CaseLinkType = CaseLinkType.related


BulkActionLiteral = Literal[
    "move",
    "add_tags",
    "remove_tags",
    "set_priority",
    "set_type",
    "set_owner",
    "set_reviewer",
    "set_automation_status",
    "deprecate",
    "archive",
    "restore",
]


class BulkRequest(_Model):
    action: BulkActionLiteral
    case_ids: list[UUID] | None = Field(default=None, max_length=5000)
    filter: dict[str, str] | None = Field(
        default=None, description="List filters (docs/06 §2.6) for 'select all matching'"
    )
    params: dict[str, Any] = Field(default_factory=dict)


class BulkSkipped(BaseModel):
    key: str
    code: str
    detail: str


class BulkResponse(BaseModel):
    bulk_operation_id: UUID
    updated: int | None = None
    skipped: list[BulkSkipped] = []
    job_id: UUID | None = Field(
        default=None, description="Set when more than 200 cases run in the background"
    )


class TagRead(BaseModel):
    id: UUID
    name: str
    is_system: bool
    usage: int


class TagCreate(_Model):
    name: str = Field(min_length=1, max_length=40)


class ResolveRead(BaseModel):
    entity_type: Literal["test_case"]
    id: UUID
    key: str


# -- comments -------------------------------------------------------------------------------------


class CommentRead(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    body: str | None
    mentions: list[UUID]
    author: UserRef | None
    created_at: datetime
    edited_at: datetime | None
    deleted: bool
    editable_until: datetime


class CommentCreate(_Model):
    entity_type: Literal["test_case", "test_case_version"]
    entity_id: UUID
    body: str = Field(min_length=1, max_length=10000)


class CommentPatch(_Model):
    body: str = Field(min_length=1, max_length=10000)
