"""Test design error codes (docs/06 §3)."""

from __future__ import annotations

from tcms.core.errors import Conflict, Forbidden, RuleViolation


class FolderCycle(RuleViolation):
    code, title = "folder_cycle", "A folder cannot be moved into its own subfolder"


class FolderTooDeep(RuleViolation):
    code, title = "folder_too_deep", "Folders can be nested at most 10 levels deep"


class FolderNotEmpty(Conflict):
    code, title = "folder_not_empty", "Only empty folders can be deleted"


class InvalidStatus(Conflict):
    code, title = "invalid_status", "This action is not possible in the current status"


class SelfApprovalNotAllowed(Forbidden):
    code, title = "self_approval_not_allowed", "You can't approve your own version"


class CaseHasRuns(Conflict):
    code, title = "case_has_runs", "The case has been included in a cycle and cannot be deleted"


class CaseArchived(Conflict):
    code, title = "case_archived", "Archived cases cannot be edited; restore the case first"
