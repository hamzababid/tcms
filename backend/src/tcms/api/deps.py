"""FastAPI dependencies shared by routers (docs/04 §3.3)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from tcms.core.config import Settings
from tcms.core.uow import UnitOfWork, unit_of_work


@dataclass
class AppState:
    settings: Settings
    session_factory: sessionmaker[Session]


def app_state(request: Request) -> AppState:
    state: AppState = request.app.state.tcms
    return state


def get_uow(request: Request) -> Iterator[UnitOfWork]:
    """One read-write transaction per request (POST/PUT/PATCH/DELETE)."""
    with unit_of_work(app_state(request).session_factory) as uow:
        yield uow


def get_read_uow(request: Request) -> Iterator[UnitOfWork]:
    """Read-only transaction for GET routes."""
    with unit_of_work(app_state(request).session_factory, read_only=True) as uow:
        yield uow
