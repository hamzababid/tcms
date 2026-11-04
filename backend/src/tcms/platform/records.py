"""The record a comment or attachment belongs to, resolved by the owning module (platform is the leaf)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RecordRef:
    entity_type: str  # e.g. "test_case", "test_case_step", "test_case_version"
    entity_id: UUID
    project_id: UUID
    label: str  # human reference for audit summaries, e.g. "SPARK-TC-12"
    write_permission: str  # permission that allows attaching to / unlinking from this record
    immutable: bool = False  # BR-28: attachments can no longer be removed (approved version, final result…)
