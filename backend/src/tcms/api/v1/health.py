"""Health endpoints (docs/06 §4.14, NFR-REL-05)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from tcms.api.deps import AppState, app_state
from tcms.platform import storage

router = APIRouter(prefix="/api/v1/health", tags=["health"])
log = structlog.get_logger()


class LiveStatus(BaseModel):
    status: Literal["ok"]


class CheckResult(BaseModel):
    ok: bool
    detail: str | None = None


class ReadyStatus(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: dict[str, CheckResult]


@router.get("/live", response_model=LiveStatus)
def live() -> LiveStatus:
    return LiveStatus(status="ok")


def _expected_head(state: AppState) -> str | None:
    cfg = Config()
    cfg.set_main_option("script_location", str(state.settings.migrations_path))
    return ScriptDirectory.from_config(cfg).get_current_head()


@dataclass(frozen=True)
class Checks:
    checks: dict[str, CheckResult]
    migration_current: str | None
    migration_head: str | None

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks.values())


def run_checks(state: AppState) -> Checks:
    """Database, migration head and object storage (readiness; also the System page, US-165)."""
    checks: dict[str, CheckResult] = {}
    current: str | None = None
    head: str | None = None
    try:
        with state.session_factory() as session:
            current = session.execute(text("select version_num from alembic_version")).scalar_one_or_none()
        checks["database"] = CheckResult(ok=True)
    except Exception as exc:
        log.warning("health.database_failed", error=str(exc).splitlines()[0])
        checks["database"] = CheckResult(ok=False, detail="database unreachable")
    if checks["database"].ok:
        try:
            head = _expected_head(state)
            checks["migrations"] = CheckResult(
                ok=current == head,
                detail=None if current == head else f"database at {current}, code expects {head}",
            )
        except Exception as exc:
            log.error("health.migration_head_failed", error=str(exc).splitlines()[0])
            checks["migrations"] = CheckResult(ok=False, detail="cannot read migration scripts")
    else:
        checks["migrations"] = CheckResult(ok=False, detail="unknown: database unreachable")
    try:
        storage.check_bucket(storage.make_client(state.settings), state.settings.s3_bucket)
        checks["storage"] = CheckResult(ok=True)
    except Exception as exc:
        log.warning("health.storage_failed", error=str(exc).splitlines()[0])
        checks["storage"] = CheckResult(ok=False, detail="object storage unreachable")
    return Checks(checks, current, head)


@router.get("/ready", response_model=ReadyStatus, responses={503: {"model": ReadyStatus}})
def ready(state: AppState = Depends(app_state)) -> JSONResponse:
    result = run_checks(state)
    body = ReadyStatus(status="ok" if result.ok else "unavailable", checks=result.checks)
    return JSONResponse(body.model_dump(), status_code=200 if result.ok else 503)
