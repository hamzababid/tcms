"""Enums, defined once (docs/04 §12) and mapped to the PostgreSQL enum types of docs/05 §2."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class ProjectStatus(StrEnum):
    active = "active"
    archived = "archived"


class ReleaseStatus(StrEnum):
    planned = "planned"
    active = "active"
    released = "released"
    archived = "archived"


class ReleaseDecisionKind(StrEnum):
    go = "go"
    go_with_risks = "go_with_risks"
    no_go = "no_go"


class PriorityLevel(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class CaseStatus(StrEnum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    deprecated = "deprecated"
    archived = "archived"


class CaseFormat(StrEnum):
    steps = "steps"
    text = "text"


class CaseType(StrEnum):
    functional = "functional"
    integration = "integration"
    end_to_end = "end_to_end"
    api = "api"
    ui = "ui"
    data_validation = "data_validation"
    performance = "performance"
    security = "security"
    compatibility = "compatibility"
    usability = "usability"


class DesignTechnique(StrEnum):
    positive = "positive"
    negative = "negative"
    boundary_value = "boundary_value"
    equivalence_partitioning = "equivalence_partitioning"
    error_guessing = "error_guessing"


class AutomationStatus(StrEnum):
    manual = "manual"
    automated = "automated"
    to_be_automated = "to_be_automated"
    not_automatable = "not_automatable"


class ApprovalMode(StrEnum):
    auto = "auto"
    manual = "manual"


class CaseLinkType(StrEnum):
    related = "related"
    duplicated_from = "duplicated_from"


class PlanType(StrEnum):
    functional = "functional"
    integration = "integration"
    regression = "regression"
    release_validation = "release_validation"
    uat = "uat"
    smoke = "smoke"
    performance = "performance"
    security = "security"


class PlanStatus(StrEnum):
    draft = "draft"
    active = "active"
    completed = "completed"
    archived = "archived"


class CycleStatus(StrEnum):
    planned = "planned"
    active = "active"
    closed = "closed"


class RunStatus(StrEnum):
    not_run = "not_run"
    in_progress = "in_progress"
    passed = "passed"
    failed = "failed"
    blocked = "blocked"
    skipped = "skipped"
    not_applicable = "not_applicable"


class ResultState(StrEnum):
    draft = "draft"
    final = "final"


class ResultStatus(StrEnum):
    passed = "passed"
    failed = "failed"
    blocked = "blocked"
    skipped = "skipped"
    not_applicable = "not_applicable"


class StepStatus(StrEnum):
    not_run = "not_run"
    passed = "passed"
    failed = "failed"
    blocked = "blocked"
    skipped = "skipped"


class ResultSource(StrEnum):
    manual = "manual"
    automation = "automation"


class DefectStatus(StrEnum):
    open = "open"
    triaged = "triaged"
    assigned = "assigned"
    in_progress = "in_progress"
    fixed = "fixed"
    ready_for_retest = "ready_for_retest"
    verified = "verified"
    closed = "closed"
    reopened = "reopened"
    rejected = "rejected"
    duplicate = "duplicate"
    cannot_reproduce = "cannot_reproduce"
    deferred = "deferred"


class DefectResolution(StrEnum):
    fixed = "fixed"
    wont_fix = "wont_fix"
    duplicate = "duplicate"
    cannot_reproduce = "cannot_reproduce"
    not_a_bug = "not_a_bug"
    deferred = "deferred"


class RequirementType(StrEnum):
    epic = "epic"
    feature = "feature"
    user_story = "user_story"
    functional = "functional"
    non_functional = "non_functional"
    business = "business"


class RequirementStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    implemented = "implemented"
    obsolete = "obsolete"


class RequirementSource(StrEnum):
    internal = "internal"
    jira = "jira"


class ActorTypeEnum(StrEnum):
    user = "user"
    api_token = "api_token"
    system = "system"
    integration = "integration"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead = "dead"


class TransferKind(StrEnum):
    import_ = "import"
    export = "export"


class TransferStatus(StrEnum):
    uploaded = "uploaded"
    validating = "validating"
    validated = "validated"
    committing = "committing"
    committed = "committed"
    generating = "generating"
    ready = "ready"
    failed = "failed"
    expired = "expired"


class ViewVisibility(StrEnum):
    private = "private"
    project = "project"


class TokenScope(StrEnum):
    read = "read"
    read_write = "read_write"


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """SQLAlchemy type bound to an existing PostgreSQL enum (created by the baseline migration)."""
    return SAEnum(
        enum_cls,
        name=name,
        create_type=False,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


# PostgreSQL type name for each enum (docs/05 §2). Used by models and by `/meta/enums`.
PG_TYPES: dict[str, type[StrEnum]] = {
    "project_status": ProjectStatus,
    "release_status": ReleaseStatus,
    "release_decision_kind": ReleaseDecisionKind,
    "priority_level": PriorityLevel,
    "case_status": CaseStatus,
    "case_format": CaseFormat,
    "case_type": CaseType,
    "design_technique": DesignTechnique,
    "automation_status": AutomationStatus,
    "approval_mode": ApprovalMode,
    "case_link_type": CaseLinkType,
    "plan_type": PlanType,
    "plan_status": PlanStatus,
    "cycle_status": CycleStatus,
    "run_status": RunStatus,
    "result_state": ResultState,
    "result_status": ResultStatus,
    "step_status": StepStatus,
    "result_source": ResultSource,
    "defect_status": DefectStatus,
    "defect_resolution": DefectResolution,
    "requirement_type": RequirementType,
    "requirement_status": RequirementStatus,
    "requirement_source": RequirementSource,
    "actor_type": ActorTypeEnum,
    "job_status": JobStatus,
    "transfer_kind": TransferKind,
    "transfer_status": TransferStatus,
    "view_visibility": ViewVisibility,
    "token_scope": TokenScope,
}


def T(name: str) -> SAEnum:
    return pg_enum(PG_TYPES[name], name)
