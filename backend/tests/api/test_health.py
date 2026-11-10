"""Health endpoints (docs/06 §4.14; TCMS-140 "Health ready fails when DB down")."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tcms.core.config import Settings
from tcms.main import create_app
from tests.conftest import Database


def _settings(db_url: str, minio: dict[str, str], bucket: str = "tcms-attachments") -> Settings:
    return Settings(
        database_url=db_url,
        s3_endpoint_url=minio["endpoint"],
        s3_access_key_id=minio["access_key"],
        s3_secret_access_key=SecretStr(minio["secret_key"]),
        s3_bucket=bucket,
    )


def test_live() -> None:
    with TestClient(create_app(Settings())) as c:
        assert c.get("/api/v1/health/live").json() == {"status": "ok"}


@pytest.mark.integration
def test_ready_when_all_dependencies_up(database: Database, minio: dict[str, str], bucket: str) -> None:
    with TestClient(create_app(_settings(database.app_url, minio, bucket))) as c:
        r = c.get("/api/v1/health/ready")
    assert r.status_code == 200, r.json()
    assert r.json()["checks"] == {
        "database": {"ok": True, "detail": None},
        "migrations": {"ok": True, "detail": None},
        "storage": {"ok": True, "detail": None},
    }


@pytest.mark.integration
def test_tcms_140_ready_fails_when_database_down(minio: dict[str, str], bucket: str) -> None:
    """TCMS-140."""
    unreachable = "postgresql+psycopg://tcms_app:x@127.0.0.1:1/tcms"
    with TestClient(create_app(_settings(unreachable, minio, bucket))) as c:
        r = c.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "unavailable"
    assert r.json()["checks"]["database"]["ok"] is False


@pytest.mark.integration
def test_ready_fails_when_bucket_missing(database: Database, minio: dict[str, str]) -> None:
    with TestClient(create_app(_settings(database.app_url, minio, "no-such-bucket"))) as c:
        r = c.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"]["storage"]["ok"] is False
