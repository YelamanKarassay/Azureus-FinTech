"""Capture reproducibility metadata for jobs and ingestion runs.

Per §3.10, every job records `code_version` (git SHA), `dependencies_lock`
(pip-freeze / uv.lock snapshot), and `git_status_clean` (dirty-tree flag).
Ingestion runs persist a compact subset (hash of the lock file, not the
full text) in `ingestion_runs.config`.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def get_git_sha() -> str | None:
    """Return current HEAD SHA, or `None` if not in a git repo."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def is_git_status_clean() -> bool:
    """`True` iff working tree is clean (no uncommitted or untracked changes).

    Defaults to `False` if not in a git repo — the safer assumption for
    reproducibility audits.
    """
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip() == ""
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def get_dependencies_lock_hash() -> str | None:
    """Return sha256 hash of `uv.lock`, or `None` if it's missing."""
    lock = _REPO_ROOT / "uv.lock"
    if not lock.exists():
        return None
    return hashlib.sha256(lock.read_bytes()).hexdigest()


def get_dependencies_lock() -> str | None:
    """Return full `uv.lock` text, or `None` if it's missing.

    Used for `jobs.dependencies_lock` (text column). Ingestion runs store
    only the hash to keep lineage rows small.
    """
    lock = _REPO_ROOT / "uv.lock"
    if not lock.exists():
        return None
    return lock.read_text(encoding="utf-8")


def capture_reproducibility() -> dict[str, Any]:
    """Compact reproducibility snapshot for `ingestion_runs.config`."""
    return {
        "code_version": get_git_sha(),
        "git_status_clean": is_git_status_clean(),
        "dependencies_lock_hash": get_dependencies_lock_hash(),
    }
