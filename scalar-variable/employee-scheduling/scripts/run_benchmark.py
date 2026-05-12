#!/usr/bin/env python3.12
"""Compatibility wrapper for the shared benchmark framework."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPO_ROOT / "src"),
    str(REPO_ROOT / "list-variable" / "cvrp" / "src"),
    str(REPO_ROOT / "scalar-variable" / "employee-scheduling" / "src"),
]

from solverforge_bench.cli import main  # noqa: E402


if __name__ == "__main__":
    main(default_benchmark="employee-scheduling")
