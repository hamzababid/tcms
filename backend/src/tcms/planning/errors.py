"""Planning error codes (docs/06 §3)."""

from __future__ import annotations

from tcms.core.errors import Conflict, RuleViolation


class PlanArchived(Conflict):
    code, title = "invalid_status", "Archived plans cannot be edited; restore the plan first"


class InvalidTransition(RuleViolation):
    code, title = "invalid_transition", "This status change is not allowed"
