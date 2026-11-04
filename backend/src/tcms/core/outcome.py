"""Outcome of a service call that must commit bookkeeping even when it fails (docs/ops/00-review.md G1).

Example: a failed sign-in records the attempt, the lockout and `auth.login_failed` audit, *then* the
API answers 401. The service returns `Outcome.fail(error)`; the router lets the UnitOfWork commit and
calls `unwrap()` afterwards, which raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from tcms.core.errors import DomainError

T = TypeVar("T")


@dataclass(frozen=True)
class Outcome(Generic[T]):
    value: T | None = None
    error: DomainError | None = None

    @classmethod
    def ok(cls, value: T) -> Outcome[T]:
        return cls(value=value)

    @classmethod
    def fail(cls, error: DomainError) -> Outcome[T]:
        return cls(error=error)

    def unwrap(self) -> T:
        if self.error is not None:
            raise self.error
        if self.value is None:
            raise RuntimeError("Outcome has neither value nor error")
        return self.value
