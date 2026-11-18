#!/usr/bin/env python3
"""Verify the SolverForge and Timefold models encode the validator's ruleset.

Both native models must name the same four constraints, carry the same
unassigned-delivery weight, and derive travel time from coordinates with the
validator's rule: Euclidean metres over ``speed_mps``, rounded half up.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SOLVER_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "delivery_scale_bench" / "solver"
)
RUST_SRC = SOLVER_DIR / "solverforge_deliveries" / "src"
JAVA_ROOT = (
    SOLVER_DIR
    / "timefold"
    / "src"
    / "main"
    / "java"
    / "com"
    / "solverforgebench"
    / "deliveries"
)

CONSTRAINTS = {
    "all_deliveries_assigned",
    "vehicle_capacity",
    "delivery_time_windows",
    "total_travel_time",
}
UNASSIGNED_DELIVERY_HARD = 1_000_000
TRAVEL_RULES = (
    (
        RUST_SRC / "adapter.rs",
        "((dx * dx + dy * dy) as f64).sqrt() / speed_mps + 0.5).floor()",
    ),
    (
        JAVA_ROOT / "domain" / "Depot.java",
        "Math.floor(Math.sqrt((double) (dx * dx + dy * dy)) / speed + 0.5)",
    ),
)
SPEED_READS = (
    (RUST_SRC / "adapter.rs", "speed_mps: f64"),
    (JAVA_ROOT / "Main.java", "Depot.useSpeed(input.speedMps)"),
)


def main() -> int:
    errors: list[str] = []
    rust = (RUST_SRC / "constraints.rs").read_text(encoding="utf-8")
    java = (JAVA_ROOT / "DeliveryConstraintProvider.java").read_text(encoding="utf-8")

    for label, names in (
        ("SolverForge", set(re.findall(r'\.named\("(\w+)"\)', rust))),
        ("Timefold", set(re.findall(r'\.asConstraint\("(\w+)"\)', java))),
    ):
        if names != CONSTRAINTS:
            errors.append(
                f"{label} constraints differ: missing {sorted(CONSTRAINTS - names)}, "
                f"extra {sorted(names - CONSTRAINTS)}"
            )

    rust_weight = re.search(r"const UNASSIGNED_DELIVERY_HARD: i64 = ([\d_]+);", rust)
    java_weight = re.search(
        r"static final long UNASSIGNED_DELIVERY_HARD = ([\d_]+)L;", java
    )
    for label, match in (("SolverForge", rust_weight), ("Timefold", java_weight)):
        if (
            match is None
            or int(match.group(1).replace("_", "")) != UNASSIGNED_DELIVERY_HARD
        ):
            errors.append(
                f"{label} unassigned-delivery weight differs from {UNASSIGNED_DELIVERY_HARD}"
            )

    for path, needle in (*TRAVEL_RULES, *SPEED_READS):
        if needle not in path.read_text(encoding="utf-8"):
            errors.append(f"{path.name} must contain the shared travel rule: {needle}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("delivery-scale model parity passed: 4 constraints, shared travel rule")
    return 0


if __name__ == "__main__":
    sys.exit(main())
