"""Bug-link API schemas (docs/06 §4.8, §5.6)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcms.bugs.rules import REFERENCE_MAX, TITLE_MAX, URL_MAX
from tcms.identity.schemas import UserRef


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseBugLinkCreate(_In):
    reference: str = Field(min_length=1, max_length=REFERENCE_MAX, examples=["SPK-431"])
    url: str | None = Field(
        default=None, max_length=URL_MAX, description="http(s) only; built from the project template if empty"
    )
    title: str | None = Field(default=None, max_length=TITLE_MAX)


class BugLinkCreate(CaseBugLinkCreate):
    step_id: UUID | None = Field(default=None, description="A step of the run's pinned version")


class BugLinkPatch(_In):
    url: str | None = Field(default=None, max_length=URL_MAX, description="Empty or null clears it")
    title: str | None = Field(default=None, max_length=TITLE_MAX)


class LinkedCase(BaseModel):
    id: UUID
    key: str
    title: str


class LinkedCycle(BaseModel):
    id: UUID
    key: str


class BugLinkRead(BaseModel):
    id: UUID
    reference: str
    url: str | None
    title: str | None
    test_case: LinkedCase
    run_id: UUID | None
    result_id: UUID | None
    step_id: UUID | None
    step_position: int | None
    cycle: LinkedCycle | None
    run_status: str | None = Field(description="Latest status of the linked run")
    attempt_no: int | None
    attempt_status: str | None = Field(description="Final status, or 'draft' while in progress")
    created_by: UserRef | None
    created_at: datetime
    can_edit: bool = Field(description="The caller may edit or remove this link")
    row_version: int


class BugSummaryRead(BaseModel):
    reference: str
    url: str | None
    title: str | None
    cases: int
    runs: int
    failing_runs: int
    needs_retest_runs: int
    cycle_keys: list[str]
    first_linked_at: datetime
    last_linked_at: datetime


class RetestRequest(_In):
    reference: str = Field(min_length=1, max_length=REFERENCE_MAX)
    dry_run: bool = Field(default=False, description="Only count the runs that would be flagged")


class RetestResponse(BaseModel):
    reference: str
    linked_runs: int
    flagged: int = Field(description="Runs flagged (or that would be, with dry_run)")
    dry_run: bool


class BugReportRead(BaseModel):
    text: str = Field(description="Markdown to paste into the team's tracker")
