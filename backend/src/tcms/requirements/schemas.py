"""Requirement-reference and traceability API schemas (docs/06 §4.9, §5.8; ADR-024)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcms.core.references import TITLE_MAX, URL_MAX
from tcms.identity.schemas import UserRef

RefStatus = Literal["not_covered", "failed", "blocked", "not_run", "passed"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementRefsCreate(_In):
    references: str = Field(
        min_length=1, max_length=20000, description="One or many: 'SPK-120, SPK-121' or one per line (≤ 500)"
    )
    url: str | None = Field(default=None, max_length=URL_MAX, description="Only for a single reference")
    title: str | None = Field(default=None, max_length=TITLE_MAX, description="Only for a single reference")


class RequirementRefPatch(_In):
    url: str | None = Field(default=None, max_length=URL_MAX, description="Empty or null clears it")
    title: str | None = Field(default=None, max_length=TITLE_MAX)


class CaseIdsRequest(_In):
    """Cases to link: ids and/or every case of folders (with subfolders) and tags (the Add cases picker)."""

    test_case_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    folder_ids: list[UUID] = Field(default_factory=list, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=50)


class ReferencesRequest(_In):
    references: str = Field(min_length=1, max_length=20000)


class LinkCasesRequest(_In):
    references: str = Field(min_length=1, max_length=20000)
    test_case_ids: list[UUID] = Field(min_length=1, max_length=1000)


class RequirementRefRead(BaseModel):
    id: UUID
    reference: str
    url: str | None
    title: str | None
    archived: bool
    case_count: int
    status: RefStatus | None = Field(
        default=None, description="Status in the requested release (or across all cycles); docs/02 §10.5"
    )
    created_at: datetime
    updated_at: datetime
    row_version: int


class RefsCreated(BaseModel):
    created: int
    references: list[RequirementRefRead]


class LinkCount(BaseModel):
    count: int
    created: int = Field(default=0, description="References registered by this request")


class LatestResult(BaseModel):
    status: str
    finished_at: datetime
    executed_by: UserRef | None
    run_id: UUID
    cycle_key: str


class BugRef(BaseModel):
    reference: str
    url: str | None


class TraceCase(BaseModel):
    id: UUID
    key: str
    title: str
    latest: LatestResult | None
    bugs: list[BugRef]


class PlanRef(BaseModel):
    id: UUID
    key: str
    name: str


class RequirementDetail(RequirementRefRead):
    cases: list[TraceCase]
    plans: list[PlanRef]


class Rate(BaseModel):
    numerator: int
    denominator: int
    value: float | None


class CoverageRead(BaseModel):
    """docs/02 §10.5 metrics; rates are null when there is nothing in scope (BR-24)."""

    total: int
    covered: int
    not_covered: int
    passed: int
    failed: int
    blocked: int
    not_run: int
    coverage: Rate
    verified: Rate


class TraceRow(BaseModel):
    """docs/06 §5.8 (ADR-024: a reference, no hierarchy)."""

    requirement: RequirementRefRead
    linked_cases: int
    status_in_release: RefStatus
    cases: list[TraceCase]
    bugs: list[BugRef]


class TraceabilityRead(BaseModel):
    release_id: UUID | None
    summary: CoverageRead
    page: int
    page_size: int
    total: int = Field(description="Rows matching the filters (the summary counts every reference)")
    rows: list[TraceRow]
