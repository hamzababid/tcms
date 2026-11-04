"""Identity error codes (docs/06 §3; additions from docs/ops/00-review.md G6)."""

from __future__ import annotations

from typing import ClassVar

from tcms.core.errors import Conflict, DomainError, Forbidden, RuleViolation, Unauthenticated


class InvalidCredentials(Unauthenticated):
    code, title = "invalid_credentials", "Email or password is incorrect"


class SessionExpired(Unauthenticated):
    code, title = "session_expired", "Your session has expired"


class MfaRequired(Unauthenticated):
    code, title = "mfa_required", "Two-step verification is required"


class InvalidMfaCode(Unauthenticated):
    code, title = "invalid_mfa_code", "The verification code is not valid"


class AccountLocked(DomainError):
    status: ClassVar[int] = 423
    code, title = "account_locked", "Too many attempts"


class MfaEnrollmentRequired(Forbidden):
    code, title = "mfa_enrollment_required", "Set up two-step verification to continue"


class TokenScopeInsufficient(Forbidden):
    code, title = "token_scope_insufficient", "This API token cannot perform write operations"


class CsrfFailed(Forbidden):
    code, title = "csrf_failed", "Missing or invalid CSRF token"


class TokenInvalid(RuleViolation):
    code, title = "token_invalid", "This link is invalid or has expired"


class PasswordPolicy(RuleViolation):
    code, title = "password_policy", "Password does not meet the policy"


class LastOrgAdmin(Conflict):
    code, title = "last_org_admin", "The organization needs at least one active administrator"


class LastQaManager(Conflict):
    code, title = "last_qa_manager", "The project needs at least one QA Manager"


class AlreadyMember(Conflict):
    code, title = "already_member", "The user is already a member of this project"


class UserExists(Conflict):
    code, title = "user_exists", "A user with this email already exists"


class MfaAlreadyEnabled(Conflict):
    code, title = "mfa_already_enabled", "Two-step verification is already enabled"


class MfaRequiredByPolicy(Conflict):
    code, title = "mfa_required_by_policy", "Two-step verification is required for your account"
