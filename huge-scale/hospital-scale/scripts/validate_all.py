#!/usr/bin/env python3
"""Prove every committed hospital-at-scale instance is hard-feasible.

Loads each instance through the benchmark loader, scores its hidden witness
with the benchmark validator, and checks every witness assignment lies in the
candidate domain the solver models receive.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hospital_scale_bench.domain.models import Solution
from hospital_scale_bench.loader import instance_entries, load_instance, load_witness
from hospital_scale_bench.solver.instance_json import skill_candidates
from hospital_scale_bench.validation import HardConstraintViolation, validate_breakdown

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "hospital"


def main() -> int:
    failures = 0
    for entry in instance_entries(DATA_DIR):
        instance = load_instance(DATA_DIR, entry)
        witness = load_witness(DATA_DIR, entry)
        if len(instance.employees) != entry["employees"]:
            print(f"{entry['name']}: employee count {len(instance.employees)}")
            failures += 1
            continue
        if len(instance.shifts) != entry["shifts"]:
            print(f"{entry['name']}: shift count {len(instance.shifts)}")
            failures += 1
            continue
        candidates = skill_candidates(instance)
        index_by_id = {
            employee.id: idx for idx, employee in enumerate(instance.employees)
        }
        outside = sum(
            index_by_id[employee_id] not in set_for
            for employee_id, set_for in zip(
                witness,
                (
                    frozenset(candidates[shift.required_skill])
                    for shift in instance.shifts
                ),
                strict=True,
            )
        )
        if outside:
            print(f"{entry['name']}: {outside} witness assignments outside the domain")
            failures += 1
            continue
        try:
            breakdown = validate_breakdown(
                solution=Solution(assignments=witness), instance=instance
            )
        except HardConstraintViolation as exc:
            print(f"{entry['name']}: witness infeasible: {exc}")
            failures += 1
            continue
        sizes = sorted(len(values) for values in candidates)
        print(
            f"{entry['name']}: feasible witness, cost {sum(breakdown.values())} "
            f"{breakdown}; candidates per skill min {sizes[0]} max {sizes[-1]}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
