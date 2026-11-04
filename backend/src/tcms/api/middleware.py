"""Request ID and access-log middleware (docs/03 §15)."""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from tcms.core.logging import request_id_var

log = structlog.get_logger()
_VALID_ID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id")
        request_id = incoming if incoming and _VALID_ID.match(incoming) else f"req_{secrets.token_hex(8)}"
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "http.request",
            request_id=request_id,
            method=request.method,
            route=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return response
