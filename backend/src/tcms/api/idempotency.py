"""`Idempotency-Key` on POST creates (docs/06 §2.8): a replay within 24 h returns the original response.

Usage in a router::

    guard: Idempotency = Depends(idempotency("create_case"))
    if (replay := guard.replay(body)) is not None:
        return replay
    result = ...
    guard.store(201, result)
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tcms.api.deps import Auth, app_state
from tcms.core.errors import RuleViolation, ValidationFailed
from tcms.identity.service import Authenticated
from tcms.platform import idempotency as saved


class IdempotencyKeyReused(RuleViolation):
    code, title = "idempotency_key_reused", "This Idempotency-Key was used with a different request"


class Idempotency:
    def __init__(self, request: Request, auth: Authenticated, endpoint: str) -> None:
        self.request = request
        self.principal = auth.token_id or auth.user_id
        self.endpoint = endpoint
        self.key = request.headers.get("idempotency-key")
        if self.key is not None and not 1 <= len(self.key) <= 200:
            raise ValidationFailed("Idempotency-Key must be 1–200 characters")
        self._hash = b""

    def replay(self, body: BaseModel | dict[str, Any] | None) -> JSONResponse | None:
        if self.key is None:
            return None
        payload = (
            body.model_dump_json() if isinstance(body, BaseModel) else repr(sorted((body or {}).items()))
        )
        self._hash = hashlib.sha256(f"{self.endpoint}|{payload}".encode()).digest()
        factory = app_state(self.request).session_factory
        with factory() as s:
            row = saved.find(s, self.principal, self.key)
            s.commit()
        if row is None:
            return None
        if row.request_hash != self._hash or row.endpoint != self.endpoint:
            raise IdempotencyKeyReused()
        return JSONResponse(row.body, status_code=row.status, headers={"Idempotency-Replayed": "true"})

    def store(self, status: int, result: Any) -> None:
        if self.key is None:
            return
        factory = app_state(self.request).session_factory
        with factory() as s:
            saved.save(
                s, self.principal, self.key, self.endpoint, self._hash, status, jsonable_encoder(result)
            )
            s.commit()


def idempotency(endpoint: str) -> Callable[..., Idempotency]:
    def dependency(request: Request, auth: Authenticated = Auth) -> Idempotency:
        return Idempotency(request, auth, endpoint)

    return dependency
