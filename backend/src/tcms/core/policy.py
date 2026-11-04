"""Organization settings (docs/02 §4.1). Owned by `workspace`; read by `identity` through this type.

Workspace builds it from `organizations.settings`; identity services receive it as a parameter so the
lower module never imports the higher one (docs/03 §5.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_ORG_SETTINGS: dict[str, Any] = {
    "mfa_required_for_all": False,
    "session_idle_minutes": 30,
    "session_absolute_hours": 12,
    "qa_managers_can_create_projects": True,
    "default_attachment_max_mb": 25,
    "audit_retention_years": 3,
}


@dataclass(frozen=True)
class OrgPolicy:
    mfa_required_for_all: bool = False
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    qa_managers_can_create_projects: bool = True
    default_attachment_max_mb: int = 25
    audit_retention_years: int = 3

    @classmethod
    def from_settings(cls, settings: dict[str, Any] | None) -> OrgPolicy:
        merged = {**DEFAULT_ORG_SETTINGS, **(settings or {})}
        return cls(**{k: merged[k] for k in DEFAULT_ORG_SETTINGS})
