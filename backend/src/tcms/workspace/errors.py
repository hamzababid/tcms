"""Workspace error codes (docs/06 §3)."""

from __future__ import annotations

from tcms.core.errors import Conflict, RuleViolation


class ProjectKeyTaken(Conflict):
    code, title = "project_key_taken", "This project key is already used in the organization"


class NameTaken(Conflict):
    code, title = "name_taken", "This name is already used"


class ProjectArchived(Conflict):
    code, title = "project_archived", "The project is archived and read-only"


class InvalidTransition(RuleViolation):
    code, title = "invalid_transition", "This status change is not allowed"


class ConfirmationMismatch(RuleViolation):
    code, title = "confirmation_mismatch", "The confirmation does not match"


class ReleaseArchived(Conflict):
    code, title = "invalid_status", "The release is archived; restore it before recording a decision"
