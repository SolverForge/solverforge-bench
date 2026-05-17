from __future__ import annotations

from pathlib import Path
from typing import Callable

from job_shop_bench.domain.models import JobShopInstance, Solution
from job_shop_bench.solver.ortools import solve_with_ortools
from solverforge_bench.model import SolverVersion
from solverforge_bench.solver_versions import (
    cargo_dependency_version,
    executable_version,
    maven_property_version,
    versions_for_solvers,
)

AVAILABLE_METHODS = ["solverforge", "timefold", "ortools"]
_SOLVER_DIR = Path(__file__).resolve().parent


def create_solver(
    method: str, time_limit: int
) -> Callable[[JobShopInstance, int], Solution]:
    if method not in AVAILABLE_METHODS:
        raise ValueError(
            f"Unknown method '{method}'. Available: {', '.join(AVAILABLE_METHODS)}"
        )

    if method == "solverforge":
        from job_shop_bench.solver.solverforge import solve_with_solverforge

        return solve_with_solverforge

    if method == "timefold":
        from job_shop_bench.solver.timefold import solve_with_timefold

        return solve_with_timefold

    return solve_with_ortools


def solver_versions(solvers: list[str]) -> dict[str, SolverVersion]:
    resolvers = {
        "solverforge": cargo_dependency_version(
            _SOLVER_DIR / "solverforge_jssp" / "Cargo.toml", "solverforge"
        ),
        "timefold": maven_property_version(
            _SOLVER_DIR / "timefold" / "pom.xml", "timefold.version"
        ),
        "ortools": executable_version(
            _SOLVER_DIR / "ortools" / "target" / "job_shop_scheduling_ortools"
        ),
    }
    return versions_for_solvers(solvers, resolvers)
