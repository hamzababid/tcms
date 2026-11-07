"""FastAPI application factory (docs/04 §1)."""

from __future__ import annotations

from fastapi import FastAPI

from tcms import platform
from tcms.api.deps import AppState
from tcms.api.middleware import RequestContextMiddleware
from tcms.api.problems import PROBLEM_RESPONSES, install_problem_handlers
from tcms.api.v1 import (
    auth,
    bugs,
    cycles,
    health,
    imports,
    meta,
    notifications,
    organization,
    plans,
    projects,
    records,
    reporting,
    requirements,
    results,
    saved_views,
    search,
    test_cases,
)
from tcms.core.config import Settings, get_settings
from tcms.core.db import app_engine, session_factory
from tcms.core.logging import configure_logging

API_VERSION = "0.1.0"


def install_modules() -> None:
    """Register writers, job handlers and in-transaction event handlers of every module."""
    platform.install()
    import tcms.bugs.service
    import tcms.execution.jobs
    import tcms.identity.jobs
    import tcms.imports.jobs
    import tcms.notifications.jobs
    import tcms.platform.attachments
    import tcms.platform.email
    import tcms.platform.transfers
    import tcms.reporting.exports
    import tcms.reporting.snapshots
    import tcms.testdesign.jobs
    import tcms.testdesign.service  # noqa: F401


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    install_modules()
    app = FastAPI(
        title=f"{settings.tcms_product_name} API",
        version=API_VERSION,
        openapi_url="/api/v1/openapi.json",
        docs_url=None if settings.is_production else "/api/v1/docs",
        redoc_url=None,
    )
    from tcms.platform import attachments, storage

    store = attachments.Storage(storage.make_client(settings), settings.s3_bucket)
    from tcms.platform import transfers

    transfers.configure(store)
    app.state.tcms = AppState(
        settings=settings, session_factory=session_factory(app_engine(settings)), store=store
    )
    app.add_middleware(RequestContextMiddleware)
    install_problem_handlers(app)
    for module in (
        health,
        auth,
        organization,
        projects,
        meta,
        test_cases,
        plans,
        cycles,
        results,
        bugs,
        requirements,
        search,
        saved_views,
        reporting,
        notifications,
        imports,
        records,
    ):
        app.include_router(module.router, responses=PROBLEM_RESPONSES)
    return app
