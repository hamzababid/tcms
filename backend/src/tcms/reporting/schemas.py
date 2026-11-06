"""Dashboards, readiness, decisions, reports and exports (docs/06 §4.3, §4.10, §4.13, §5.9)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcms.execution.schemas import ExecutionSummaryRead, KeyRef, RateRead, Ref
from tcms.identity.schemas import UserRef
from tcms.requirements.schemas import CoverageRead

DecisionKind = Literal["go", "go_with_risks", "no_go"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# -- readiness and decisions -----------------------------------------------------------------------


class PlanBrief(BaseModel):
    id: UUID
    key: str
    name: str


class RuleRead(BaseModel):
    type: str
    threshold: float
    params: dict[str, Any]
    actual: RateRead | None = Field(description="Percentage rules and tag_fully_executed")
    count: int | None = Field(description="Count rules (max_failed, max_blocked)")
    met: bool
    note: str | None = Field(description="Why the value is undefined (D2: undefined is not met)")
    plan: PlanBrief | None = Field(description="The plan the rule comes from; null = default rule")


class PlanReadiness(BaseModel):
    plan: PlanBrief
    ready: bool


class DecisionRead(BaseModel):
    id: UUID
    decision: DecisionKind
    comment: str
    risks: str | None
    decided_by: UserRef | None
    decided_at: datetime
    ready: bool = Field(description="Readiness at the time of the decision (from the snapshot)")


class DecisionDetail(DecisionRead):
    snapshot: dict[str, Any] = Field(description="Rule results and metrics frozen at decision time")


class DecisionCreate(_Model):
    decision: DecisionKind
    comment: str = Field(min_length=1, max_length=20000)
    risks: str | None = Field(default=None, max_length=20000)


class ReadinessRead(BaseModel):
    """docs/06 §5.9."""

    release: Ref | None
    plan: KeyRef | None
    ready: bool
    uses_defaults: bool
    rules: list[RuleRead]
    plans: list[PlanReadiness]
    summary: ExecutionSummaryRead
    coverage: CoverageRead
    latest_decision: DecisionRead | None
    evaluated_at: datetime


class ReleaseListItem(BaseModel):
    id: UUID
    name: str
    status: str
    start_date: date | None
    target_date: date | None
    released_at: datetime | None
    summary: ExecutionSummaryRead
    ready: bool | None = Field(description="Evaluated for planned and active releases only")
    latest_decision: DecisionRead | None
    plan_count: int
    cycle_count: int


# -- dashboards ------------------------------------------------------------------------------------


class BugMetricsRead(BaseModel):
    linked: int
    on_failing_runs: int
    failures_without_bug: int


class BugRowRead(BaseModel):
    reference: str
    url: str | None
    title: str | None
    failing_runs: int
    runs: int


class CycleWidget(BaseModel):
    id: UUID
    key: str
    name: str
    status: str
    release: Ref | None
    environment: Ref
    start_date: date | None
    due_date: date | None
    overdue: bool
    summary: ExecutionSummaryRead


class TesterRead(BaseModel):
    user: UserRef | None = Field(description="null = the unassigned pool")
    assigned: int
    executed: int
    remaining: int
    failed: int
    blocked: int


class UncoveredRef(BaseModel):
    id: UUID
    reference: str
    title: str | None
    url: str | None


class RepositoryRead(BaseModel):
    total_cases: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_automation: dict[str, int]
    approved: RateRead
    automation_coverage: RateRead
    folders: int
    plans_by_status: dict[str, int]


class ReadinessBrief(BaseModel):
    release: Ref
    ready: bool
    met: int
    total: int
    uses_defaults: bool


class ManagerDashboard(BaseModel):
    """docs/02 §11.3 QA Manager dashboard = project Overview (docs/07 §5.3)."""

    release: Ref | None
    readiness: ReadinessBrief | None
    summary: ExecutionSummaryRead
    retest_count: int
    bugs: BugMetricsRead
    top_bugs: list[BugRowRead]
    cycles: list[CycleWidget]
    coverage: CoverageRead
    top_uncovered: list[UncoveredRef]
    regression: ExecutionSummaryRead
    team: list[TesterRead]
    repository: RepositoryRead


class TrendDay(BaseModel):
    day: date
    executed: int
    passed: int
    failed: int
    blocked: int
    pass_rate: RateRead
    bug_links_added: int
    failed_runs: int
    req_total: int
    req_covered: int
    req_passed: int
    live: bool = Field(description="Today, computed live (not a stored snapshot)")


class ModuleBugs(BaseModel):
    folder_id: UUID
    name: str
    references: int


class ReleaseQuality(BaseModel):
    release: Ref
    status: str
    released_at: datetime | None
    pass_rate_applicable: RateRead
    failed_at_release: int | None = Field(
        description="Failed runs on the release day (snapshot); null if none"
    )
    bug_references: int
    coverage: RateRead
    regression: ExecutionSummaryRead


class QualityDashboard(BaseModel):
    """docs/02 §11.3 project quality dashboard."""

    release: Ref | None
    date_from: date
    date_to: date
    days: list[TrendDay]
    bugs_by_module: list[ModuleBugs]
    automation: RepositoryRead
    releases: list[ReleaseQuality]
    last_snapshot_day: date | None


class OrgProjectRow(BaseModel):
    project: KeyRef
    active_cycles: int
    summary: ExecutionSummaryRead
    failed: int
    bugs_on_failing_runs: int
    last_activity: datetime | None


class OrgDashboard(BaseModel):
    projects: list[OrgProjectRow]


class RefreshRead(BaseModel):
    job_id: UUID | None
    queued: bool


# -- reports and exports ---------------------------------------------------------------------------


class ReportColumn(BaseModel):
    key: str
    label: str
    kind: Literal["text", "int", "datetime", "date"]


class ReportRead(BaseModel):
    report: str
    title: str
    columns: list[ReportColumn]
    filters: list[str]
    items: list[dict[str, Any]]
    page: int
    page_size: int
    total: int


class ExportRequest(_Model):
    format: Literal["csv", "xlsx"]
    filters: dict[str, str] = Field(default_factory=dict, description="The report's query parameters")


class TransferRead(BaseModel):
    id: UUID
    kind: str
    entity: str
    status: str
    format: str
    summary: dict[str, Any]
    errors: list[Any]
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    download_url: str | None


class ExportAccepted(BaseModel):
    transfer_id: UUID
    rows: int
