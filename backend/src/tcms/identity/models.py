"""Identity tables (docs/05 §3.1). Private to the identity module."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import TS, UUIDT, StdColumns, created_ts, pk
from tcms.core.db import Base
from tcms.core.enums import T, TokenScope


class User(StdColumns, Base):
    __tablename__ = "users"
    __audit_type__ = "user"
    __table_args__ = (Index("ux_users__email", "email", unique=True),)

    id: Mapped[UUID] = pk()
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    time_zone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(TS)
    last_login_at: Mapped[datetime | None] = mapped_column(TS)
    password_changed_at: Mapped[datetime | None] = mapped_column(TS)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (Index("ux_organization_members__user_id", "user_id", unique=True),)

    organization_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), primary_key=True)
    is_org_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    joined_at: Mapped[datetime] = created_ts()
    granted_by: Mapped[UUID | None] = mapped_column(UUIDT)


class Role(StdColumns, Base):
    __tablename__ = "roles"
    # ux_roles__organization_id_code is an expression index (coalesce); see migrations/env.py.

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission: Mapped[str] = mapped_column(Text, primary_key=True)


class UserMfa(Base):
    __tablename__ = "user_mfa"

    user_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), primary_key=True)
    totp_secret_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    enrolled_at: Mapped[datetime] = created_ts()
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"
    __table_args__ = (Index("ix_mfa_recovery_codes__user_id", "user_id"),)

    id: Mapped[UUID] = pk()
    user_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = created_ts()


class SessionRow(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ux_sessions__token_hash", "token_hash", unique=True),
        Index("ix_sessions__user_id", "user_id"),
        Index("ix_sessions__expires_at", "expires_at"),
    )

    id: Mapped[UUID] = pk()
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    user_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("organizations.id"), nullable=False)
    created_at: Mapped[datetime] = created_ts()
    last_seen_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    mfa_failed_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (Index("ix_auth_rate_limits__window_start", "window_start"),)

    bucket_key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(TS, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ux_password_reset_tokens__token_hash", "token_hash", unique=True),)

    id: Mapped[UUID] = pk()
    user_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = created_ts()


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts__email_occurred", "email", "occurred_at"),
        Index("ix_login_attempts__ip_occurred", "ip", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(CITEXT)
    ip: Mapped[str | None] = mapped_column(INET)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    occurred_at: Mapped[datetime] = created_ts()


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __audit_type__ = "api_token"
    __table_args__ = (
        Index("ux_api_tokens__token_hash", "token_hash", unique=True),
        Index("ix_api_tokens__user_id", "user_id"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    token_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    scope: Mapped[TokenScope] = mapped_column(T("token_scope"), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("projects.id"))
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = created_ts()


class Invitation(Base):
    __tablename__ = "invitations"
    __audit_type__ = "invitation"
    __table_args__ = (
        Index("ux_invitations__token_hash", "token_hash", unique=True),
        Index("ix_invitations__organization_id_email", "organization_id", "email"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    is_org_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    project_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("projects.id"))
    role_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("roles.id"))
    invited_by: Mapped[UUID | None] = mapped_column(UUIDT)
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = created_ts()


class ProjectMember(Base):
    __tablename__ = "project_members"
    __audit_type__ = "membership"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "project_id"], ["projects.organization_id", "projects.id"]),
        Index("ix_project_members__user_id", "user_id"),
    )

    project_id: Mapped[UUID] = mapped_column(UUIDT, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    role_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("roles.id"), nullable=False)
    granted_by: Mapped[UUID | None] = mapped_column(UUIDT)
    granted_at: Mapped[datetime] = created_ts()
