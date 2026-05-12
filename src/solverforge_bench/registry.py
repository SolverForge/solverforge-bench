"""Benchmark spec registry."""

from __future__ import annotations

from solverforge_bench.model import BenchmarkSpec


def get_specs() -> dict[str, BenchmarkSpec]:
    from cvrp_bench.spec import SPEC as cvrp
    from employee_scheduling_bench.spec import SPEC as employee_scheduling

    return {
        "cvrp": cvrp,
        "employee-scheduling": employee_scheduling,
    }


def canonical_specs() -> list[BenchmarkSpec]:
    specs = get_specs()
    return [specs["cvrp"], specs["employee-scheduling"]]
