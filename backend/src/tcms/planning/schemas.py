"""Planning API schemas (docs/06 §4.5)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcms.core.enums import CycleStatus, PlanStatus, PlanType
from tcms.identity.schemas import UserRef
from tcms.planning.rules import MD_MAX, NAME_MAX, NAME_MIN

MD = Field(default=None, max_length=MD_MAX)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Risk(_Model):
    description: str = Field(min_length=1, max_length=2000)
    impact: str = Field(pattern="^(low|medium|high)$")
    mitigation: str | None = Field(default=None, max_length=2000)


RuleType = Literal[
    "min_execution_progress",
    "min_pass_rate",
    "min_pass_rate_applicable",
    "max_failed",
    "max_blocked",
    "min_requirement_coverage",
    "min_requirements_verified",
    "tag_fully_executed",
]


class ExitRuleParams(_Model):
    severities: list[Literal["critical", "high", "medium", "low"]] | None = None
    tag: str | None = Field(default=None, max_length=40)


class ExitRule(_Model):
    """A readiness rule (docs/02 §11.4, docs/06 §5.9 shape); evaluated in M7.

    Percentage rules take a fraction 0–1; `max_*` rules take a count."""

    type: RuleType
    threshold: float = Field(ge=0)
    params: ExitRuleParams | None = None


class PlanCreate(_Model):
    name: str = Field(min_length=NAME_MIN, max_length=NAME_MAX)
    type: PlanType
    release_id: UUID | None = None
    objectives: str | None = MD
    scope_in: str | None = MD
    scope_out: str | None = MD
    entry_criteria: str | None = MD
    exit_criteria_notes: str | None = MD
    acceptance_criteria: str | None = MD
    exit_rules: list[ExitRule] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    environment_ids: list[UUID] = Field(default_factory=list)
    member_ids: list[UUID] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    owner_id: UUID | None = None


class PlanPatch(_Model):
    name: str | None = Field(default=None, min_length=NAME_MIN, max_length=NAME_MAX)
    type: PlanType | None = None
    status: PlanStatus | None = None
    release_id: UUID | None = None
    objectives: str | None = MD
    scope_in: str | None = MD
    scope_out: str | None = MD
    entry_criteria: str | None = MD
    exit_criteria_notes: str | None = MD
    acceptance_criteria: str | None = MD
    exit_rules: list[ExitRule] | None = None
    risks: list[Risk] | None = None
    environment_ids: list[UUID] | None = None
    member_ids: list[UUID] | None = None
    start_date: date | None = None
    end_date: date | None = None
    owner_id: UUID | None = None
    row_version: int | None = None


class AddCasesRequest(_Model):
    case_ids: list[UUID] | None = None
    folder_ids: list[UUID] | None = None
    include_subfolders: bool = True
    tags: list[str] | None = None
    saved_view_id: UUID | None = None  # Q2: accepted but rejected (422) until M6


class CaseIdsRequest(_Model):
    case_ids: list[UUID] = Field(min_length=1)


class RequirementIdsRequest(_Model):
    requirement_ids: list[UUID] = Field(min_length=1)


class CloneRequest(_Model):
    name: str | None = Field(default=None, min_length=NAME_MIN, max_length=NAME_MAX)


class Skipped(BaseModel):
    key: str
    reason: str


class AddCasesResponse(BaseModel):
    added: int
    skipped: list[Skipped]


class CountResponse(BaseModel):
    count: int


class PlanCycle(BaseModel):
    """A cycle created from the plan (plan detail › Cycles, docs/07 §5.7)."""

    id: UUID
    key: str
    name: str
    status: CycleStatus
    total: int
    executed: int
    passed: int


class PlanRead(BaseModel):
    id: UUID
    key: str
    project_id: UUID
    name: str
    type: PlanType
    status: PlanStatus
    release_id: UUID | None
    objectives: str | None
    scope_in: str | None
    scope_out: str | None
    entry_criteria: str | None
    exit_criteria_notes: str | None
    acceptance_criteria: str | None
    exit_rules: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    environment_ids: list[UUID]
    member_ids: list[UUID]
    owner: UserRef | None
    start_date: date | None
    end_date: date | None
    case_count: int
    requirement_count: int
    allowed_transitions: list[PlanStatus] = Field(
        description="Statuses this plan may move to via PATCH (archive has its own action)."
    )
    archived: bool
    created_at: datetime
    updated_at: datetime
    row_version: int
    # ?include=cases,requirements,cycles (docs/06 §4.5)
    case_ids: list[UUID] | None = None
    requirement_ids: list[UUID] | None = None
    cycles: list[PlanCycle] | None = None


class PlanListItem(BaseModel):
    id: UUID
    key: str
    name: str
    type: PlanType
    status: PlanStatus
    release_id: UUID | None
    owner: UserRef | None
    case_count: int
    start_date: date | None
    end_date: date | None
    archived: bool
    updated_at: datetime
    row_version: int


class PlanCaseResult(BaseModel):
    cycle_id: UUID
    cycle_key: str
    status: str


class PlanCaseItem(BaseModel):
    case_id: UUID
    key: str
    title: str
    status: str
    priority: str
    folder_id: UUID
    results: list[PlanCaseResult] = Field(description="Run status in each cycle created from the plan")
