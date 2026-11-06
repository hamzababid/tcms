"""Bug-link error codes (docs/06 §3)."""

from __future__ import annotations

from tcms.core.errors import Conflict, RuleViolation


class AlreadyLinked(Conflict):
    code, title = "already_linked", "This bug is already linked here"


class BugLinkRequired(RuleViolation):
    code, title = "bug_link_required", "Link a bug before finishing a failed run"
