"""Application settings (docs/03 §16). Everything comes from the environment."""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from tcms.core.crypto import KeyRing

_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class Environment(StrEnum):
    local = "local"
    test = "test"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    tcms_env: Environment = Environment.local
    tcms_product_name: str = "Assay"
    tcms_base_url: str = "http://localhost:5173"
    tcms_secret_key: SecretStr = SecretStr("")
    tcms_encryption_keys: SecretStr = SecretStr("")

    database_url: str = "postgresql+psycopg://tcms_app:change-me-app@localhost:5432/tcms"
    database_maintenance_url: str = "postgresql+psycopg://tcms_owner:change-me-owner@localhost:5432/tcms"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_statement_timeout_ms_api: int = 15_000
    db_statement_timeout_ms_worker: int = 300_000

    s3_endpoint_url: str | None = None
    s3_bucket: str = "tcms-attachments"
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_region: str = "us-east-1"
    attachments_presigned_downloads: bool = False

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "Assay <no-reply@localhost>"
    smtp_starttls: bool = False

    worker_concurrency: int = Field(default=4, ge=1, le=64)
    worker_poll_interval_seconds: float = 1.0
    log_level: str = "INFO"
    session_cookie_secure: bool = True
    rate_limit_auth_per_min: int = 20
    rate_limit_per_min: int = 600  # per session, API token or (anonymous) client IP; 0 turns it off
    feature_flags: str = ""

    migrations_path: Path = _BACKEND_ROOT / "migrations"

    @property
    def is_production(self) -> bool:
        return self.tcms_env is Environment.production

    @property
    def secret_key_bytes(self) -> bytes:
        raw = self.tcms_secret_key.get_secret_value()
        if len(raw) < 32:
            raise RuntimeError("TCMS_SECRET_KEY must be set (at least 32 characters)")
        return raw.encode()

    @property
    def keyring(self) -> KeyRing:
        return KeyRing.parse(self.tcms_encryption_keys.get_secret_value())

    @property
    def origin(self) -> str:
        """Scheme + host + port of TCMS_BASE_URL (CSRF origin check)."""
        from urllib.parse import urlsplit

        parts = urlsplit(self.tcms_base_url)
        return f"{parts.scheme}://{parts.netloc}"


def secret_file_values(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """`NAME_FILE=/run/secrets/x` sets setting `name` from that file (production compose, docs/ops/deploy.md):
    secrets stay out of the environment and `docker inspect`. A trailing newline is dropped."""
    env = os.environ if environ is None else environ
    out: dict[str, str] = {}
    for name in Settings.model_fields:
        path = env.get(f"{name.upper()}_FILE")
        if path:
            out[name] = Path(path).read_text(encoding="utf-8").rstrip("\r\n")
    return out


@lru_cache
def get_settings() -> Settings:
    return Settings(**secret_file_values())  # type: ignore[arg-type]
