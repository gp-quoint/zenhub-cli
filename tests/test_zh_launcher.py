"""Regression tests for the bash `zh` launcher (Python + uv entrypoint)."""

from __future__ import annotations

import os
import subprocess
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ZH_SCRIPT = REPO_ROOT / "zh"


def test_launcher_via_symlink_does_not_recurse_uv(tmp_path: Path) -> None:
    """~/.local/bin/zh symlink must resolve to the repo, not uv-run loop."""
    link = tmp_path / "zh"
    link.symlink_to(ZH_SCRIPT)
    proc = subprocess.run(
        [str(link), "version"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
    )
    combined = proc.stdout + proc.stderr
    assert "recursively invoked" not in combined
    assert proc.returncode == 0, combined
    assert combined.strip()


def test_launcher_ignores_ambient_uv_project_environment(tmp_path: Path) -> None:
    """direnv UV_PROJECT_ENVIRONMENT must not steal uv run from zenhub-cli."""
    foreign = tmp_path / "foreign-venv"
    venv.create(foreign, with_pip=False, clear=True)
    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = str(foreign)
    env["VIRTUAL_ENV"] = str(foreign)
    env["UV_PROJECT"] = str(tmp_path)
    env["PYTHONPATH"] = str(tmp_path / "not-zh-src")
    proc = subprocess.run(
        [str(ZH_SCRIPT), "version"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
        env=env,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "ModuleNotFoundError" not in combined
    assert "zh version" in combined or combined.strip()
