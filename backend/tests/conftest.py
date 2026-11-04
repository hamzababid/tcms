"""Shared fixtures (docs/08 §3): a migrated PostgreSQL 16 per test worker, MinIO, app clients.

The database container is started once per pytest-xdist worker. It is initialised exactly like a
deployment: `docs/schema/00_roles.sql` as superuser, then `alembic upgrade head` as tcms_owner.
Tests connect as `tcms_app` (the application role) unless they test owner-only behaviour.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
SCHEMA_DIR = REPO_ROOT / "docs" / "schema"
PG_IMAGE = "postgres:16"
MINIO_IMAGE = "cgr.dev/chainguard/minio:latest"  # Docker Hub no longer publishes minio/minio

APP_PASSWORD = "change-me-app"  # placeholders from docs/schema/00_roles.sql (test containers only)
OWNER_PASSWORD = "change-me-owner"


@dataclass(frozen=True)
class Database:
    container: object
    host: str
    port: int

    def url(self, role: str, password: str, db: str = "tcms") -> str:
        return f"postgresql+psycopg://{role}:{password}@{self.host}:{self.port}/{db}"

    @property
    def app_url(self) -> str:
        return self.url("tcms_app", APP_PASSWORD)

    @property
    def owner_url(self) -> str:
        return self.url("tcms_owner", OWNER_PASSWORD)

    def psql(self, *args: str, user: str = "postgres", db: str = "postgres", password: str = "test") -> str:
        """Run psql inside the container (the schema directory is mounted at /schema)."""
        result = self.container.exec(  # type: ignore[attr-defined]
            [
                "env",
                f"PGPASSWORD={password}",
                "psql",
                "-h",
                "localhost",
                "-U",
                user,
                "-d",
                db,
                "-v",
                "ON_ERROR_STOP=1",
                *args,
            ]
        )
        output = result.output.decode()
        if result.exit_code != 0:
            raise RuntimeError(f"psql failed ({result.exit_code}):\n{output}")
        return output


def _alembic(owner_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": owner_url}
    return subprocess.run(
        ["uv", "run", "--quiet", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def database() -> Iterator[Database]:
    from testcontainers.community.postgres import PostgresContainer

    container = PostgresContainer(PG_IMAGE, username="postgres", password="test", dbname="postgres")
    container.with_volume_mapping(str(SCHEMA_DIR), "/schema", "ro")
    container.start()
    try:
        db = Database(container, container.get_container_host_ip(), int(container.get_exposed_port(5432)))
        db.psql("-q", "-f", "/schema/00_roles.sql")
        db.psql("-q", "-c", "CREATE DATABASE tcms OWNER tcms_owner")
        result = _alembic(db.owner_url, "upgrade", "head")
        if result.returncode != 0:
            raise RuntimeError(f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}")
        yield db
    finally:
        container.stop()


@pytest.fixture(scope="session")
def app_engine(database: Database) -> Iterator[Engine]:
    engine = create_engine(database.app_url, pool_size=5, max_overflow=5)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def owner_engine(database: Database) -> Iterator[Engine]:
    engine = create_engine(database.owner_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def session_factory(app_engine: Engine) -> sessionmaker[Session]:
    from tcms import platform

    platform.install()
    return sessionmaker(bind=app_engine, expire_on_commit=False)


@pytest.fixture
def db_session(app_engine: Engine) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after the test."""
    connection = app_engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def clean_jobs(app_engine: Engine) -> Iterator[None]:
    """Jobs tests commit for real; leave the queue empty before and after."""
    with app_engine.begin() as conn:
        conn.execute(text("DELETE FROM jobs"))
    yield
    with app_engine.begin() as conn:
        conn.execute(text("DELETE FROM jobs"))


@pytest.fixture(scope="session")
def minio() -> Iterator[dict[str, str]]:
    from testcontainers.community.minio import MinioContainer

    container = MinioContainer(MINIO_IMAGE)
    container.start()
    try:
        cfg = container.get_config()
        yield {
            "endpoint": f"http://{cfg['endpoint']}",
            "access_key": cfg["access_key"],
            "secret_key": cfg["secret_key"],
        }
    finally:
        container.stop()


@pytest.fixture(scope="session")
def bucket(minio: dict[str, str]) -> str:
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=minio["endpoint"],
        aws_access_key_id=minio["access_key"],
        aws_secret_access_key=minio["secret_key"],
        region_name="us-east-1",
    )
    s3.create_bucket(Bucket="tcms-attachments")
    return "tcms-attachments"


@pytest.fixture(scope="session")
def stack_settings(database: Database, minio: dict[str, str], bucket: str) -> object:
    """Settings pointing at the test database (as tcms_app) and MinIO."""
    from pydantic import SecretStr

    from tcms.core.config import Settings

    return Settings(
        database_url=database.app_url,
        s3_endpoint_url=minio["endpoint"],
        s3_access_key_id=minio["access_key"],
        s3_secret_access_key=SecretStr(minio["secret_key"]),
        s3_bucket=bucket,
    )
