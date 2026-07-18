from __future__ import annotations

import hashlib
import json
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


def load_solver_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("rb") as config_file:
        return tomllib.load(config_file)


def solver_config_policy_sha256(config_path: Path) -> str:
    config = load_solver_config(config_path)
    canonical = json.dumps(config, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def solver_config_for_time_limit(config_path: Path, time_limit: int) -> dict[str, Any]:
    """Load an adapter-owned SolverForge config and overlay the run budget."""
    config = deepcopy(load_solver_config(config_path))
    termination = config.setdefault("termination", {})
    if not isinstance(termination, dict):
        raise ValueError(f"{config_path}: termination must be a TOML table")
    termination.pop("minutes_spent_limit", None)
    termination["seconds_spent_limit"] = max(1, int(time_limit))
    return config
