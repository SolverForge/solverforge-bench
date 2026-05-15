#!/usr/bin/env python3.14
"""Unified benchmark suite entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

from _venv_bootstrap import ensure_repo_venv


REPO_ROOT = Path(__file__).resolve().parents[1]
ensure_repo_venv(REPO_ROOT)
sys.path[:0] = [
    str(REPO_ROOT / "src"),
    str(REPO_ROOT / "list-variable" / "cvrp" / "src"),
    str(REPO_ROOT / "scalar-variable" / "employee-scheduling" / "src"),
]

from solverforge_bench.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
