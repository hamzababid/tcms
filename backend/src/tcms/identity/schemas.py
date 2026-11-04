"""Identity request/response models (docs/06 §4.1, §4.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tcms.core.enums import ProjectStatus

RoleCodeLiteral = Literal["qa_manager", "qa_lead", "qa_engineer", "developer", "pm_ba", "viewer"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _valid_tz(v: str | None) -> str | None:
    if v is not None and v not in available_timezones():
        raise ValueError("unknown IANA time zone")
    return v


class UserRef(BaseModel):
    id: UUID
    display_name: str
    email: str
    is_active: bool


# -- auth -----------------------------------------------------------------------------------------


class LoginRequest(_Model):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class LoginResponse(BaseModel):
    mfa_required: bool
    mfa_enrollment_required: bool


class MfaVerifyRequest(_Model):
    code: str | None = Field(default=None, max_length=10)
    recovery_code: str | None = Field(default=None, max_length=40)


class ProjectBrief(BaseModel):
    id: UUID
    key: str
    name: str
    status: ProjectStatus


class RoleBrief(BaseModel):
    code: str
    name: str


class MembershipRead(BaseModel):
    project: ProjectBrief
    role: RoleBrief
    permissions: list[str]


class OrganizationBrief(BaseModel):
    id: UUID
    name: str
    slug: str


class MfaStatus(BaseModel):
    enrolled: bool
    required: bool


class MeResponse(BaseModel):
    user: UserRef
    time_zone: str
    organization: OrganizationBrief
    is_org_admin: bool
    mfa: MfaStatus
    memberships: list[MembershipRead]
    org_permissions: list[str]


class ProfilePatch(_Model):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    time_zone: str | None = None

    _tz = field_validator("time_zone")(_valid_tz)


class PasswordChangeRequest(_Model):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


class ForgotPasswordRequest(_Model):
    email: str = Field(max_length=254)


class ResetPasswordRequest(_Model):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(max_length=1024)
    revoke_api_tokens: bool = False


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    setup_token: str


class MfaEnableRequest(_Model):
    setup_token: str = Field(max_length=500)
    code: str = Field(min_length=6, max_length=6)


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class MfaDisableRequest(_Model):
    password: str = Field(max_length=1024)
    code: str = Field(min_length=6, max_length=6)


class PasswordConfirmRequest(_Model):
    password: str = Field(max_length=1024)


class InvitationInfo(BaseModel):
    email: str
    organization: OrganizationBrief
    inviter: str | None
    project: ProjectBrief | None
    expires_at: datetime


class AcceptInvitationRequest(_Model):
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(max_length=1024)
    time_zone: str = "UTC"

    _tz = field_validator("time_zone")(_valid_tz)


class SessionRead(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool


# -- API tokens -----------------------------------------------------------------------------------


class ApiTokenCreate(_Model):
    name: str = Field(min_length=1, max_length=100)
    scope: Literal["read", "read_write"]
    expires_in_days: int = Field(default=90, ge=1, le=365)
    project_id: UUID | None = None


class ApiTokenRead(BaseModel):
    id: UUID
    name: str
    token_prefix: str
    scope: Literal["read", "read_write"]
    project_id: UUID | None
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiTokenCreated(ApiTokenRead):
    token: str = Field(description="Shown once; store it now")


# -- organization administration ------------------------------------------------------------------


class InvitationCreate(_Model):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        from tcms.identity.rules import email_problem

        v = v.strip().lower()
        problem = email_problem(v)
        if problem:
            raise ValueError(problem.message)
        return v

    is_org_admin: bool = False
    project_id: UUID | None = None
    role_code: RoleCodeLiteral | None = None


class InvitationRead(BaseModel):
    id: UUID
    email: str
    is_org_admin: bool
    project_id: UUID | None
    role_code: str | None
    invited_by: UserRef | None
    created_at: datetime
    expires_at: datetime
    expired: bool


class InvitationCreated(InvitationRead):
    accept_url: str = Field(description="Shown once (copy-link fallback when email is unavailable)")


class OrgMemberRead(BaseModel):
    user: UserRef
    is_org_admin: bool
    mfa_enrolled: bool
    last_login_at: datetime | None
    joined_at: datetime
    projects: int


class OrgMemberPatch(_Model):
    is_org_admin: bool


class ResetMfaRequest(_Model):
    reason: str = Field(min_length=1, max_length=1000)


class RoleRead(BaseModel):
    code: str
    name: str
    permissions: list[str]


class RevokedCount(BaseModel):
    revoked: int


# -- project members ------------------------------------------------------------------------------


class ProjectMemberRead(BaseModel):
    user: UserRef
    role: RoleBrief
    granted_at: datetime


class MemberAdd(_Model):
    user_id: UUID
    role_code: RoleCodeLiteral | None = None


class MemberPatch(_Model):
    role_code: RoleCodeLiteral
