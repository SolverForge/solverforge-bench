"""Benchmark spec registry."""

from __future__ import annotations

from solverforge_bench.model import BenchmarkSpec


def get_specs() -> dict[str, BenchmarkSpec]:
    from cvrp_bench.spec import SPEC as cvrp
    from delivery_scale_bench.spec import SPEC as delivery_scale
    from employee_scheduling_bench.spec import SPEC as employee_scheduling
    from hospital_scale_bench.spec import SPEC as hospital_scale
    from job_shop_bench.spec import SPEC as job_shop

    return {
        "cvrp": cvrp,
        "employee-scheduling": employee_scheduling,
        "job-shop-scheduling": job_shop,
        "hospital-scale": hospital_scale,
        "delivery-scale": delivery_scale,
    }


def canonical_specs() -> list[BenchmarkSpec]:
    specs = get_specs()
    return [
        specs["cvrp"],
        specs["employee-scheduling"],
        specs["job-shop-scheduling"],
        specs["hospital-scale"],
        specs["delivery-scale"],
    ]
