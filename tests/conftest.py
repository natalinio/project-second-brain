"""Every test runs against a scratch copy of the repository, never the working tree."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "*.duckdb",
                                "*.duckdb.wal", "_extracted")


@pytest.fixture()
def brain(tmp_path: Path) -> Path:
    dst = tmp_path / "brain"
    shutil.copytree(REPO, dst, ignore=IGNORE)
    return dst


def py(root: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=root, input=stdin, capture_output=True,
                          text=True, encoding="utf-8")
