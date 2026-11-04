"""US-006: import-linter fails on a forbidden import (docs/03 §5.2)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _lint(src: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(src)}
    return subprocess.run(
        ["uv", "run", "--quiet", "lint-imports", "--config", str(BACKEND / "pyproject.toml"), "--no-cache"],
        cwd=src,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_current_code_respects_contracts() -> None:
    result = _lint(BACKEND / "src")
    assert result.returncode == 0, result.stdout + result.stderr


def test_private_models_import_is_rejected(tmp_path: Path) -> None:
    shutil.copytree(BACKEND / "src" / "tcms", tmp_path / "tcms")
    (tmp_path / "tcms" / "defects" / "leak.py").write_text(
        "from tcms.execution.models import TestRun  # noqa\n"
    )
    result = _lint(tmp_path)
    assert result.returncode != 0
    assert "execution: models and repository are private BROKEN" in result.stdout


def test_upward_dependency_is_rejected(tmp_path: Path) -> None:
    shutil.copytree(BACKEND / "src" / "tcms", tmp_path / "tcms")
    (tmp_path / "tcms" / "workspace" / "upward.py").write_text("import tcms.execution.service  # noqa\n")
    (tmp_path / "tcms" / "execution" / "service.py").write_text("")
    result = _lint(tmp_path)
    assert result.returncode != 0
    assert "Module dependency layers (docs/03 §5.1) BROKEN" in result.stdout
