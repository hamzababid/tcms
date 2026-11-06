"""Execution error codes (docs/06 §3)."""

from __future__ import annotations

from tcms.core.errors import Conflict, RuleViolation


class CycleClosed(Conflict):
    code, title = "cycle_closed", "This cycle is closed"


class RunHasResults(Conflict):
    code, title = "run_has_results", "This run has results and cannot be changed this way"


class RunSuperseded(Conflict):
    code, title = "run_superseded", "This run has been superseded"


class AlreadyLatest(Conflict):
    code, title = "already_latest", "The run is already pinned to the latest eligible version"


class InvalidStatus(Conflict):
    code, title = "invalid_status", "This action is not possible in the current status"


class DraftExists(Conflict):
    """BR-07 on start: another tester's draft (take-over needs cycle.manage)."""

    code, title = "draft_exists", "Someone else is running this attempt"


class DraftsExist(Conflict):
    code, title = "draft_exists", "Finalize or discard the draft attempts before closing"


class NoEligibleVersion(RuleViolation):
    code, title = "no_eligible_version", "The case has no version that can be added"


class ReasonRequired(RuleViolation):
    code, title = "reason_required", "A reason is required"
