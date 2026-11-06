"""Execution events for modules above execution (docs/03 §5.4; ADR-023).

Both are dispatched at once inside the producing transaction, so a handler can veto the change
(finalize) or clean up rows that reference the attempt before it is deleted (discard).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from tcms.core.events import DomainEvent

if TYPE_CHECKING:
    from tcms.core.context import AccessContext


@dataclass(frozen=True)
class ResultFinalizing(DomainEvent):
    """Before an attempt becomes final with `status`. The bugs module enforces
    `require_bug_link_for_failure` (422 `bug_link_required`)."""

    ctx: AccessContext  # the caller's project context (audit actor, scoping)
    result_id: UUID
    status: str


@dataclass(frozen=True)
class DraftDiscarding(DomainEvent):
    """Before a draft attempt is deleted (discard, or closing a cycle with drafts)."""

    ctx: AccessContext
    result_id: UUID
    reason: str
