"""SQLAlchemy engine, session factories and the declarative base."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from tcms.core.config import Settings


class Base(DeclarativeBase):
    """Base for every ORM model. Tables are created by migrations, never by `create_all`."""

    metadata = MetaData()


def make_engine(
    url: str, *, statement_timeout_ms: int, pool_size: int = 10, max_overflow: int = 10
) -> Engine:
    connect_args: dict[str, Any] = {"options": f"-c statement_timeout={statement_timeout_ms}"}
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def app_engine(settings: Settings, *, worker: bool = False) -> Engine:
    timeout = settings.db_statement_timeout_ms_worker if worker else settings.db_statement_timeout_ms_api
    return make_engine(
        settings.database_url,
        statement_timeout_ms=timeout,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)
