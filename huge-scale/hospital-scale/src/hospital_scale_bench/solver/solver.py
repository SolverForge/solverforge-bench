"""Hospital-at-scale solver registry."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from hospital_scale_bench.domain.models import Instance
from solverforge_bench.model import SolverResult, SolverVersion
from solverforge_bench.solver_versions import (
    cargo_dependency_version,
    maven_property_version,
    versions_for_solvers,
)

SolverFn = Callable[[Instance, int], SolverResult]
AVAILABLE_METHODS = ["solverforge", "timefold"]
DEFAULT_METHODS = ["solverforge", "timefold"]
_SOLVER_DIR = Path(__file__).resolve().parent


def _load_solverforge() -> SolverFn:
    from hospital_scale_bench.solver.solverforge import solve_with_solverforge

    return solve_with_solverforge


def _load_timefold() -> SolverFn:
    from hospital_scale_bench.solver.timefold import solve_with_timefold

    return solve_with_timefold


def solver_versions(methods: Iterable[str]) -> dict[str, SolverVersion]:
    resolvers = {
        "solverforge": cargo_dependency_version(
            _SOLVER_DIR / "solverforge_hospital" / "Cargo.toml",
            "solverforge",
            runtime_distribution="solverforge-hospital-scale",
            solver_config_path=_SOLVER_DIR / "solverforge_hospital" / "solver.toml",
        ),
        "timefold": maven_property_version(
            _SOLVER_DIR / "timefold" / "pom.xml",
            "timefold.version",
            artifact=_SOLVER_DIR
            / "timefold"
            / "target"
            / "timefold-hospital-scale.jar",
        ),
    }
    return versions_for_solvers(methods, resolvers)


def create_solver(method: str, *, time_limit: int = 60) -> SolverFn:
    if method == "solverforge":
        return _load_solverforge()
    if method == "timefold":
        return _load_timefold()
    raise ValueError(
        f"Unknown method '{method}'. Available: {', '.join(AVAILABLE_METHODS)}"
    )
