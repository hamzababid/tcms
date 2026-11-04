"""US-002: every error is problem+json with a stable code and request_id (docs/06 §3)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from tcms.core import errors
from tcms.core.config import Settings
from tcms.main import create_app

router = APIRouter(prefix="/api/v1/_test")


class Body(BaseModel):
    name: str = Field(min_length=3)
    steps: list[str] = Field(min_length=1)


@router.post("/validate")
def validate(body: Body) -> dict[str, str]:
    return {"name": body.name}


CASES: list[tuple[type[errors.DomainError], int, str]] = [
    (errors.NotFound, 404, "not_found"),
    (errors.Conflict, 409, "conflict"),
    (errors.StaleRowVersion, 409, "stale_row_version"),
    (errors.RuleViolation, 422, "rule_violation"),
    (errors.ValidationFailed, 422, "validation_error"),
    (errors.RowVersionRequired, 428, "row_version_required"),
    (errors.InvalidFilter, 400, "invalid_filter"),
    (errors.InvalidSort, 400, "invalid_sort"),
    (errors.Unauthenticated, 401, "unauthenticated"),
    (errors.FileTooLarge, 413, "file_too_large"),
    (errors.UnsupportedFileType, 415, "unsupported_file_type"),
    (errors.RateLimited, 429, "rate_limited"),
    (errors.Unavailable, 503, "unavailable"),
]


@router.get("/raise/{index}")
def raise_error(index: int) -> None:
    cls = CASES[index][0]
    raise cls("specific detail")


@router.get("/permission")
def raise_permission() -> None:
    raise errors.PermissionDenied("cycle.manage")


@router.get("/catalog-code")
def raise_catalog_code() -> None:
    raise errors.RuleViolation(
        "Steps 4 and 5 have no result",
        code="incomplete_attempt",
        errors=[errors.FieldError("steps[3].status", "not_recorded", "Step 4 has no result")],
    )


@router.get("/crash")
def crash() -> None:
    raise RuntimeError("unexpected")


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(database_url="postgresql+psycopg://x:y@127.0.0.1:1/none"))
    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _assert_problem(response: object, status: int, code: str) -> dict[str, object]:
    r = response
    assert r.status_code == status  # type: ignore[attr-defined]
    assert r.headers["content-type"] == "application/problem+json"  # type: ignore[attr-defined]
    body: dict[str, object] = r.json()  # type: ignore[attr-defined]
    assert body["status"] == status
    assert body["code"] == code
    assert str(body["type"]).endswith("/" + code)
    assert str(body["request_id"]).startswith("req_")
    return body


def test_unknown_route_is_problem_json(client: TestClient) -> None:
    r = client.get("/api/v1/does-not-exist")
    body = _assert_problem(r, 404, "not_found")
    assert body["instance"] == "/api/v1/does-not-exist"
    assert r.headers["x-request-id"] == body["request_id"]


def test_request_id_is_propagated(client: TestClient) -> None:
    r = client.get("/api/v1/nope", headers={"X-Request-ID": "req_abc123"})
    assert r.json()["request_id"] == "req_abc123"
    assert r.headers["x-request-id"] == "req_abc123"


def test_validation_error_has_field_pointers(client: TestClient) -> None:
    r = client.post("/api/v1/_test/validate", json={"name": "ab", "steps": []})
    body = _assert_problem(r, 422, "validation_error")
    fields = {e["field"] for e in body["errors"]}  # type: ignore[union-attr, index]
    assert fields == {"name", "steps"}


@pytest.mark.parametrize(("index", "status", "code"), [(i, s, c) for i, (_, s, c) in enumerate(CASES)])
def test_domain_errors_map_to_status_and_code(client: TestClient, index: int, status: int, code: str) -> None:
    body = _assert_problem(client.get(f"/api/v1/_test/raise/{index}"), status, code)
    assert body["detail"] == "specific detail"


def test_permission_denied_names_required_permission(client: TestClient) -> None:
    body = _assert_problem(client.get("/api/v1/_test/permission"), 403, "permission_denied")
    assert body["required_permission"] == "cycle.manage"


def test_family_error_with_catalog_code(client: TestClient) -> None:
    body = _assert_problem(client.get("/api/v1/_test/catalog-code"), 422, "incomplete_attempt")
    assert body["errors"] == [
        {"field": "steps[3].status", "code": "not_recorded", "message": "Step 4 has no result"}
    ]


def test_unhandled_error_is_internal_problem(client: TestClient) -> None:
    body = _assert_problem(client.get("/api/v1/_test/crash"), 500, "internal_error")
    assert "unexpected" not in str(body)


def test_method_not_allowed(client: TestClient) -> None:
    _assert_problem(client.delete("/api/v1/health/live"), 405, "method_not_allowed")
