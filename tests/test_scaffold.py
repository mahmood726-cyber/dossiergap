"""Task 1 — project scaffold tests."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_package_imports():
    import dossiergap  # noqa
    assert dossiergap.__version__ == "0.1.0"


def test_cli_help_returns_zero():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "dossiergap", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "dossiergap" in result.stdout.lower()


def test_cli_preflight_subcommand_runs():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "dossiergap", "preflight"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=60,
    )
    # exit 0 or 1 are both valid here; we only assert the command dispatched
    assert result.returncode in (0, 1), f"unexpected exit: {result.returncode} — {result.stderr}"
    assert "preflight" in result.stdout.lower()


def test_gitignore_excludes_progress_md():
    gi = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "PROGRESS.md" in gi


def test_gitignore_excludes_cache_and_pdfs():
    gi = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "cache/" in gi
    assert "*.pdf" in gi


def test_pyproject_declares_required_deps():
    pp = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for dep in ("pdfplumber", "requests", "pydantic"):
        assert dep in pp, f"missing {dep} in pyproject.toml"
