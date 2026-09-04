"""Pinned official JSPLIB best-known reference values."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


REFERENCE_FILE = "best_known_solutions.json"


@lru_cache(maxsize=4)
def load_reference_catalog(data_dir: str) -> dict[str, Any]:
    """Load the versioned ScheduleOpt JSPLIB reference catalog."""

    path = Path(data_dir) / REFERENCE_FILE
    return json.loads(path.read_text(encoding="utf-8"))


def reference_for(data_dir: Path, instance: str) -> dict[str, Any]:
    """Return the official reference entry for a local JSPLIB instance."""

    catalog = load_reference_catalog(str(data_dir))
    try:
        return catalog["instances"][instance]
    except KeyError as exc:
        raise ValueError(
            f"JSPLIB instance {instance!r} has no pinned official reference"
        ) from exc
