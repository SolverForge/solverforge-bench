"""Delivery-at-scale solver registry."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from delivery_scale_bench.domain.models import Instance
from solverforge_bench.model import SolverResult, SolverVersion
from solverforge_bench.solver_versions import (
    cargo_dependency_version,
    executable_version,
    maven_property_version,
    python_distribution_version,
    versions_for_solvers,
)

SolverFn = Callable[[Instance, int], SolverResult]
AVAILABLE_METHODS = ["solverforge", "timefold", "ortools", "pyvrp"]
DEFAULT_METHODS = ["solverforge", "timefold", "ortools", "pyvrp"]
_SOLVER_DIR = Path(__file__).resolve().parent


def _load_solverforge() -> SolverFn:
    from delivery_scale_bench.solver.solverforge import solve_with_solverforge

    return solve_with_solverforge


def _load_timefold() -> SolverFn:
    from delivery_scale_bench.solver.timefold import solve_with_timefold

    return solve_with_timefold


def _load_ortools() -> SolverFn:
    from delivery_scale_bench.solver.ortools import solve_with_ortools

    return solve_with_ortools


def _load_pyvrp() -> SolverFn:
    from delivery_scale_bench.solver.pyvrp import solve_with_pyvrp

    return solve_with_pyvrp


def solver_versions(methods: Iterable[str]) -> dict[str, SolverVersion]:
    resolvers = {
        "solverforge": cargo_dependency_version(
            _SOLVER_DIR / "solverforge_deliveries" / "Cargo.toml",
            "solverforge",
            runtime_distribution="solverforge-delivery-scale",
            solver_config_path=_SOLVER_DIR / "solverforge_deliveries" / "solver.toml",
        ),
        "timefold": maven_property_version(
            _SOLVER_DIR / "timefold" / "pom.xml",
            "timefold.version",
            artifact=_SOLVER_DIR
            / "timefold"
            / "target"
            / "timefold-delivery-scale.jar",
        ),
        "ortools": executable_version(
            _SOLVER_DIR / "ortools" / "target" / "delivery_scale_ortools"
        ),
        "pyvrp": python_distribution_version("pyvrp"),
    }
    return versions_for_solvers(methods, resolvers)


def create_solver(method: str, *, time_limit: int = 300) -> SolverFn:
    if method == "solverforge":
        return _load_solverforge()
    if method == "timefold":
        return _load_timefold()
    if method == "ortools":
        return _load_ortools()
    if method == "pyvrp":
        return _load_pyvrp()
    raise ValueError(
        f"Unknown method '{method}'. Available: {', '.join(AVAILABLE_METHODS)}"
    )
