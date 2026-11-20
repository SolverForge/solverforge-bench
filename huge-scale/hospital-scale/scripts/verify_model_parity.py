#!/usr/bin/env python3
"""Verify every hospital-scale solver model encodes the validator's ruleset.

The SolverForge and Timefold models must name the same nine constraints and
carry the same weight constants as the benchmark validator. The OR-Tools CP-SAT
model states the hard rules as constraints, so it carries only the rest and
preference constants, which must match the validator's. All three models read
the candidate domain from the shared ``skill_candidates`` document instead of
deriving their own.
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
ORTOOLS_MAIN = SOLVER_DIR / "ortools" / "main.cc"

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
ORTOOLS_WEIGHTS = {
    "MINIMUM_REST_MINUTES": validation.MINIMUM_REST_MINUTES,
    "PREFERENCE_SOFT": validation.PREFERENCE_WEIGHT,
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


def cpp_constants(text: str) -> dict[str, int]:
    return {
        name: int(value.replace("'", ""))
        for name, value in re.findall(r"constexpr int64_t ([A-Z_]+) = ([\d']+);", text)
        if name in ORTOOLS_WEIGHTS
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

    ortools = ORTOOLS_MAIN.read_text(encoding="utf-8")
    if cpp_constants(ortools) != ORTOOLS_WEIGHTS:
        errors.append(
            f"OR-Tools weights {cpp_constants(ortools)} differ from {ORTOOLS_WEIGHTS}"
        )
    if 'root.at("skill_candidates")' not in ortools:
        errors.append("OR-Tools adapter must read the shared skill_candidates domain")

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
    print(
        "hospital-scale model parity passed: 9 constraints, identical weights, "
        "OR-Tools rest and preference constants"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
