"""Settings from secret files (M8c, docs/ops/deploy.md)."""

from __future__ import annotations

from pathlib import Path

from tcms.core.config import Settings, secret_file_values


def test_name_file_variables_read_secrets_from_files(tmp_path: Path) -> None:
    key = tmp_path / "secret_key"
    key.write_text("s" * 40 + "\n")
    url = tmp_path / "database_url"
    url.write_text("postgresql+psycopg://tcms_app:pw@db:5432/tcms")
    values = secret_file_values(
        {"TCMS_SECRET_KEY_FILE": str(key), "DATABASE_URL_FILE": str(url), "UNRELATED_FILE": "/nope"}
    )
    assert values == {
        "tcms_secret_key": "s" * 40,
        "database_url": "postgresql+psycopg://tcms_app:pw@db:5432/tcms",
    }
    settings = Settings(**values)  # type: ignore[arg-type]
    assert settings.secret_key_bytes == b"s" * 40
