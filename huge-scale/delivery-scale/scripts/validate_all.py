#!/usr/bin/env python3
"""Prove every committed delivery-at-scale instance is hard-feasible.

Loads each instance through the benchmark loader and scores its hidden witness
with the benchmark validator.
"""

from __future__ import annotations

import sys
from pathlib import Path

from delivery_scale_bench.domain.models import Solution
from delivery_scale_bench.loader import instance_entries, load_instance, load_witness
from delivery_scale_bench.validation import HardConstraintViolation, validate_breakdown

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "deliveries"


def main() -> int:
    failures = 0
    for entry in instance_entries(DATA_DIR):
        instance = load_instance(DATA_DIR, entry)
        routes = load_witness(DATA_DIR, entry)
        if len(instance.deliveries) != entry["deliveries"]:
            print(f"{entry['name']}: delivery count {len(instance.deliveries)}")
            failures += 1
            continue
        try:
            breakdown = validate_breakdown(
                solution=Solution(routes=routes), instance=instance
            )
        except HardConstraintViolation as exc:
            print(f"{entry['name']}: witness infeasible: {exc}")
            failures += 1
            continue
        print(
            f"{entry['name']}: feasible witness, {len(routes)} routes on "
            f"{instance.vehicle_count} vehicles, cost {sum(breakdown.values())}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
