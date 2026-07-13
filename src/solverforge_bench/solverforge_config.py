from __future__ import annotations

import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


def solver_config_for_time_limit(config_path: Path, time_limit: int) -> dict[str, Any]:
    """Load an adapter-owned SolverForge config and overlay the run budget."""
    with config_path.open("rb") as config_file:
        loaded = tomllib.load(config_file)

    config = deepcopy(loaded)
    termination = config.setdefault("termination", {})
    if not isinstance(termination, dict):
        raise ValueError(f"{config_path}: termination must be a TOML table")
    termination.pop("minutes_spent_limit", None)
    termination["seconds_spent_limit"] = max(1, int(time_limit))
    return config
