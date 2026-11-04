"""FastAPI application factory (docs/04 §1)."""

from __future__ import annotations

from fastapi import FastAPI

from tcms import platform
from tcms.api.deps import AppState
from tcms.api.middleware import RequestContextMiddleware
from tcms.api.problems import install_problem_handlers
from tcms.api.v1 import health
from tcms.core.config import Settings, get_settings
from tcms.core.db import app_engine, session_factory
from tcms.core.logging import configure_logging

API_VERSION = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    platform.install()
    app = FastAPI(
        title=f"{settings.tcms_product_name} API",
        version=API_VERSION,
        openapi_url="/api/v1/openapi.json",
        docs_url=None if settings.is_production else "/api/v1/docs",
        redoc_url=None,
    )
    app.state.tcms = AppState(settings=settings, session_factory=session_factory(app_engine(settings)))
    app.add_middleware(RequestContextMiddleware)
    install_problem_handlers(app)
    app.include_router(health.router)
    return app
