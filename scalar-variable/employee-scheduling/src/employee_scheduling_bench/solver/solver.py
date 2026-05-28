from pathlib import Path
from typing import Callable, Iterable

from employee_scheduling_bench.domain.models import Instance
from employee_scheduling_bench.solver.ortools import solve_with_ortools
from solverforge_bench.model import SolverResult, SolverVersion
from solverforge_bench.solver_versions import (
    cargo_dependency_version,
    executable_version,
    maven_property_version,
    versions_for_solvers,
)

SolverFn = Callable[[Instance, int], SolverResult]
AVAILABLE_METHODS = ["solverforge", "timefold", "ortools"]
_SOLVER_DIR = Path(__file__).resolve().parent


def _load_solverforge() -> SolverFn:
    from employee_scheduling_bench.solver.solverforge import solve_with_solverforge

    return solve_with_solverforge


def _load_timefold() -> SolverFn:
    from employee_scheduling_bench.solver.timefold import solve_with_timefold

    return solve_with_timefold


def solver_versions(methods: Iterable[str]) -> dict[str, SolverVersion]:
    resolvers = {
        "solverforge": cargo_dependency_version(
            _SOLVER_DIR / "solverforge_nrp" / "Cargo.toml", "solverforge"
        ),
        "timefold": maven_property_version(
            _SOLVER_DIR / "timefold" / "pom.xml", "timefold.version"
        ),
        "ortools": executable_version(
            _SOLVER_DIR / "ortools" / "target" / "employee_scheduling_ortools"
        ),
    }
    return versions_for_solvers(methods, resolvers)


def create_solver(method: str, *, time_limit: int = 60) -> SolverFn:
    if method not in AVAILABLE_METHODS:
        raise ValueError(
            f"Unknown method '{method}'. Available: {', '.join(AVAILABLE_METHODS)}"
        )

    if method == "solverforge":
        return _load_solverforge()

    if method == "timefold":
        return _load_timefold()

    solvers: dict[str, SolverFn] = {
        "ortools": solve_with_ortools,
    }

    return solvers[method]
