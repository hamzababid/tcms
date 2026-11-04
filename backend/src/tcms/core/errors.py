"""Domain errors with stable codes (docs/06 §3). Mapped to RFC 9457 problems by the API layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass(frozen=True)
class FieldError:
    field: str
    code: str
    message: str


class DomainError(Exception):
    status: ClassVar[int] = 400
    code: ClassVar[str] = "bad_request"
    title: ClassVar[str] = "Bad request"

    def __init__(
        self,
        detail: str = "",
        *,
        errors: list[FieldError] | None = None,
        code: str | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.errors = errors or []
        self.extra = extra
        if code is not None:
            # Allows a family class (e.g. RuleViolation) to carry a specific catalog code.
            self.code = code  # type: ignore[misc]


class BadRequest(DomainError):
    status, code, title = 400, "bad_request", "Bad request"


class InvalidFilter(BadRequest):
    code, title = "invalid_filter", "Unknown or invalid filter"


class InvalidSort(BadRequest):
    code, title = "invalid_sort", "Unknown or invalid sort field"


class InvalidInclude(BadRequest):
    code, title = "invalid_include", "Unknown include"


class Unauthenticated(DomainError):
    status, code, title = 401, "unauthenticated", "Authentication required"


class PermissionDenied(DomainError):
    status, code, title = 403, "permission_denied", "Permission denied"

    def __init__(self, permission: str, detail: str = "") -> None:
        super().__init__(detail or f"Requires permission {permission}", required_permission=permission)
        self.permission = permission


class Forbidden(DomainError):
    """403 with a specific catalog code (e.g. self_approval_not_allowed)."""

    status, code, title = 403, "forbidden", "Forbidden"


class NotFound(DomainError):
    status, code, title = 404, "not_found", "Not found"


class Conflict(DomainError):
    status, code, title = 409, "conflict", "Conflict"


class StaleRowVersion(Conflict):
    code, title = "stale_row_version", "This item was changed by someone else"


class ImmutableRecord(Conflict):
    code, title = "immutable_record", "This record cannot be changed"


class FileTooLarge(DomainError):
    status, code, title = 413, "file_too_large", "File is too large"


class UnsupportedFileType(DomainError):
    status, code, title = 415, "unsupported_file_type", "File type is not allowed"


class ValidationFailed(DomainError):
    status, code, title = 422, "validation_error", "Validation failed"


class RuleViolation(DomainError):
    status, code, title = 422, "rule_violation", "Business rule violated"


class RowVersionRequired(DomainError):
    status, code, title = 428, "row_version_required", "row_version is required"


class RateLimited(DomainError):
    status, code, title = 429, "rate_limited", "Too many requests"


class Unavailable(DomainError):
    status, code, title = 503, "unavailable", "A dependency is unavailable"
