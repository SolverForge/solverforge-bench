#!/usr/bin/env python3
"""Verify the SolverForge and Timefold models encode the validator's ruleset.

Both native models must name the same nine constraints, carry the same weight
constants as the benchmark validator, and read the candidate domain from the
shared ``skill_candidates`` document instead of deriving their own.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from hospital_scale_bench import validation

SOLVER_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "hospital_scale_bench" / "solver"
)
RUST_CONSTRAINTS = SOLVER_DIR / "solverforge_hospital" / "src" / "constraints.rs"
RUST_ADAPTER = SOLVER_DIR / "solverforge_hospital" / "src" / "adapter.rs"
JAVA_ROOT = (
    SOLVER_DIR
    / "timefold"
    / "src"
    / "main"
    / "java"
    / "com"
    / "solverforgebench"
    / "hospital"
)
JAVA_CONSTRAINTS = JAVA_ROOT / "HospitalConstraintProvider.java"
JAVA_MAIN = JAVA_ROOT / "Main.java"

CONSTRAINTS = {
    "assigned_shift",
    "required_skill",
    "overlapping_shift",
    "minimum_rest",
    "one_shift_per_day",
    "unavailable_employee",
    "undesired_day",
    "desired_day",
    "balance_assignments",
}
WEIGHTS = {
    "ASSIGNED_SHIFT_HARD": 1,
    "REQUIRED_SKILL_HARD": 10,
    "STRUCTURAL_MINUTE_HARD": 20,
    "ONE_SHIFT_PER_DAY_HARD": 20,
    "MINIMUM_REST_MINUTES": validation.MINIMUM_REST_MINUTES,
    "PREFERENCE_SOFT": validation.PREFERENCE_WEIGHT,
}


def rust_constants(text: str) -> dict[str, int]:
    return {
        name: int(value.replace("_", ""))
        for name, value in re.findall(r"const (\w+): i64 = ([\d_]+);", text)
    }


def java_constants(text: str) -> dict[str, int]:
    return {
        name: int(value)
        for name, value in re.findall(r"static final long (\w+) = (\d+)L;", text)
    }


def main() -> int:
    errors: list[str] = []
    rust = RUST_CONSTRAINTS.read_text(encoding="utf-8")
    java = JAVA_CONSTRAINTS.read_text(encoding="utf-8")

    for label, names in (
        ("SolverForge", set(re.findall(r'\.named\("(\w+)"\)', rust))),
        ("Timefold", set(re.findall(r'\.asConstraint\("(\w+)"\)', java))),
    ):
        if names != CONSTRAINTS:
            errors.append(
                f"{label} constraints differ: missing {sorted(CONSTRAINTS - names)}, "
                f"extra {sorted(names - CONSTRAINTS)}"
            )

    for label, constants in (
        ("SolverForge", rust_constants(rust)),
        ("Timefold", java_constants(java)),
    ):
        if constants != WEIGHTS:
            errors.append(f"{label} weights {constants} differ from {WEIGHTS}")

    if "skill_candidates" not in RUST_ADAPTER.read_text(encoding="utf-8"):
        errors.append(
            "SolverForge adapter must read the shared skill_candidates domain"
        )
    if "skill_candidates" not in JAVA_MAIN.read_text(encoding="utf-8"):
        errors.append("Timefold adapter must read the shared skill_candidates domain")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("hospital-scale model parity passed: 9 constraints, identical weights")
    return 0


if __name__ == "__main__":
    sys.exit(main())
