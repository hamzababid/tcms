"""RFC 9457 problem+json responses (docs/06 §3)."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

from tcms.core.errors import DomainError
from tcms.core.logging import request_id_var

log = structlog.get_logger()

PROBLEM_TYPE_BASE = "https://assay.dev/problems/"
MEDIA_TYPE = "application/problem+json"


class ProblemFieldError(BaseModel):
    field: str
    code: str
    message: str


class Problem(BaseModel):
    """Error body for every non-2xx response."""

    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
    errors: list[ProblemFieldError] = []


_PROBLEM_CONTENT: dict[str, Any] = {MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}}

# Every route documents problem+json errors (docs/06 §3); Schemathesis checks responses against it.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"description": "Validation or business-rule error", "model": Problem, "content": _PROBLEM_CONTENT},
    "default": {"description": "Error (application/problem+json)", "model": Problem, "content": _PROBLEM_CONTENT},
}

_HTTP_CODES = {
    400: ("bad_request", "Bad request"),
    401: ("unauthenticated", "Authentication required"),
    403: ("permission_denied", "Permission denied"),
    404: ("not_found", "Not found"),
    405: ("method_not_allowed", "Method not allowed"),
    409: ("conflict", "Conflict"),
    413: ("file_too_large", "File is too large"),
    415: ("unsupported_file_type", "Unsupported media type"),
    429: ("rate_limited", "Too many requests"),
}


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": PROBLEM_TYPE_BASE + code,
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "instance": request.url.path,
        "request_id": request_id_var.get() or getattr(request.state, "request_id", None),
        "errors": errors or [],
    }
    if extra:
        body.update({k: v for k, v in extra.items() if k not in body})
    return JSONResponse(body, status_code=status, media_type=MEDIA_TYPE, headers=headers)


def _pointer(loc: tuple[Any, ...]) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
    out = ""
    for p in parts:
        out += f"[{p}]" if p.isdigit() else (f".{p}" if out else p)
    return out or ".".join(str(p) for p in loc)


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers = {"Retry-After": str(exc.extra["retry_after"])} if "retry_after" in exc.extra else None
        return problem_response(
            request,
            status=exc.status,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            errors=[{"field": e.field, "code": e.code, "message": e.message} for e in exc.errors],
            extra=_jsonable(exc.extra),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": _pointer(tuple(e.get("loc", ()))),
                "code": str(e.get("type", "invalid")),
                "message": e.get("msg", ""),
            }
            for e in exc.errors()
        ]
        return problem_response(
            request,
            status=422,
            code="validation_error",
            title="Validation failed",
            detail=None,
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, title = _HTTP_CODES.get(exc.status_code, ("http_error", "HTTP error"))
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail.lower() != title.lower() else None
        headers = dict(exc.headers or {})
        if exc.status_code == 405:
            headers["Allow"] = ", ".join(_allowed_methods(app, request))
        return problem_response(
            request, status=exc.status_code, code=code, title=title, detail=detail, headers=headers
        )

    @app.exception_handler(DBAPIError)
    async def db_error(request: Request, exc: DBAPIError) -> JSONResponse:
        message = str(exc.orig) if exc.orig is not None else ""
        if message.startswith("immutable_record"):
            # Services must prevent this; a surfaced one is a bug (docs/05 §4).
            log.error("db.immutable_record_surfaced", error=message.splitlines()[0])
            return problem_response(
                request, status=409, code="immutable_record", title="This record cannot be changed"
            )
        log.exception("db.error")
        return problem_response(request, status=500, code="internal_error", title="Internal error")

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("request.unhandled_error")
        return problem_response(request, status=500, code="internal_error", title="Internal error")


def _allowed_methods(app: FastAPI, request: Request) -> list[str]:
    """All methods registered for the request path (FastAPI registers one route per method)."""
    from starlette.routing import Match

    methods: set[str] = set()
    for route in app.router.routes:
        match, _ = route.matches({**request.scope, "method": "GET"})
        route_methods = getattr(route, "methods", None)
        if route_methods and match is not Match.NONE:
            # Match.PARTIAL means "path matches, method differs"; FULL means GET itself is registered.
            methods |= set(route_methods)
    return sorted(methods - {"HEAD"} | ({"HEAD"} if "GET" in methods else set()))


def _jsonable(extra: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in extra.items():
        if v is None or isinstance(v, str | int | float | bool | list | dict):
            out[k] = v
        else:
            out[k] = str(v)
    return out
