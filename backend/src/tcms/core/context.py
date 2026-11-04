"""Principal and AccessContext (docs/04 §3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from tcms.core.errors import PermissionDenied


class ActorType(StrEnum):
    user = "user"
    api_token = "api_token"
    system = "system"
    integration = "integration"


@dataclass(frozen=True)
class Principal:
    user_id: UUID | None
    organization_id: UUID
    is_org_admin: bool
    display_name: str | None = None
    token_id: UUID | None = None
    token_scope: frozenset[str] | None = None
    actor_type: ActorType = ActorType.user

    @classmethod
    def system(cls, organization_id: UUID, name: str = "system") -> Principal:
        return cls(
            user_id=None,
            organization_id=organization_id,
            is_org_admin=True,
            display_name=name,
            actor_type=ActorType.system,
        )


@dataclass(frozen=True)
class RequestMeta:
    request_id: str
    ip: str | None = None
    user_agent: str | None = None


@dataclass
class AccessContext:
    principal: Principal
    project_id: UUID | None
    permissions: frozenset[str]
    request_id: str
    ip: str | None = None
    user_agent: str | None = None
    project_status: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def for_principal(
        cls,
        principal: Principal,
        meta: RequestMeta,
        *,
        project_id: UUID | None = None,
        permissions: frozenset[str] = frozenset(),
    ) -> AccessContext:
        return cls(
            principal=principal,
            project_id=project_id,
            permissions=permissions,
            request_id=meta.request_id,
            ip=meta.ip,
            user_agent=meta.user_agent,
        )

    @property
    def pid(self) -> UUID:
        """The context project; raises for org-level contexts (programming error)."""
        if self.project_id is None:
            raise RuntimeError("project context required")
        return self.project_id

    @property
    def meta(self) -> RequestMeta:
        return RequestMeta(self.request_id, self.ip, self.user_agent)

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise PermissionDenied(permission)
