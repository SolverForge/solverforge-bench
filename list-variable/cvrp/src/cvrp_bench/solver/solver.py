from pathlib import Path
from typing import Callable, Iterable

from cvrp_bench.domain.models import Instance
from cvrp_bench.solver.ortools import solve_with_ortools
from cvrp_bench.solver.pyhygese import solve_with_pyhygese
from cvrp_bench.solver.pyvrp import solve_with_pyvrp
from cvrp_bench.solver.vroom import solve_with_vroom
from solverforge_bench.model import SolverResult, SolverVersion
from solverforge_bench.solver_versions import (
    cargo_dependency_version,
    executable_version,
    maven_property_version,
    python_distribution_version,
    versions_for_solvers,
)


AVAILABLE_METHODS = [
    "pyvrp",
    "ortools",
    "vroom",
    "timefold",
    "rustvrp",
    "pyhygese",
    "solverforge",
    "solverforge-py",
]
DEFAULT_METHODS = [
    "pyvrp",
    "ortools",
    "vroom",
    "timefold",
    "rustvrp",
    "pyhygese",
    "solverforge",
]


_SOLVER_DIR = Path(__file__).resolve().parent


def _load_rustvrp():
    from cvrp_bench.solver.rustvrp.rustvrp import solve_with_rustvrp

    return solve_with_rustvrp


def _load_timefold():
    from cvrp_bench.solver.timefold import solve_with_timefold

    return solve_with_timefold


def _load_solverforge():
    from cvrp_bench.solver.solverforge import solve_with_solverforge

    return solve_with_solverforge


def _load_solverforge_py():
    from cvrp_bench.solver.solverforge_py import solve_with_solverforge_py

    return solve_with_solverforge_py


# Type alias for solver functions
SolverFn = Callable[[Instance, int], SolverResult]


def solver_versions(methods: Iterable[str]) -> dict[str, SolverVersion]:
    resolvers = {
        "pyvrp": python_distribution_version("pyvrp"),
        "ortools": executable_version(
            _SOLVER_DIR / "ortools" / "target" / "cvrp_ortools"
        ),
        "vroom": executable_version(_SOLVER_DIR / "vroom" / "target" / "cvrp_vroom"),
        "timefold": maven_property_version(
            _SOLVER_DIR / "timefold" / "pom.xml", "timefold.version"
        ),
        "rustvrp": cargo_dependency_version(
            _SOLVER_DIR / "rustvrp" / "Cargo.toml", "vrp-cli"
        ),
        "pyhygese": python_distribution_version("hygese"),
        "solverforge": cargo_dependency_version(
            _SOLVER_DIR / "solverforge" / "Cargo.toml", "solverforge"
        ),
        "solverforge-py": python_distribution_version("solverforge"),
    }
    return versions_for_solvers(methods, resolvers)


def create_solver(method: str, *, time_limit: int = 60) -> SolverFn:
    """
    Factory function that returns a configured solver function.

    Args:
        method: One of 'pyvrp', 'ortools', 'vroom', 'timefold', 'rustvrp',
            'pyhygese', 'solverforge', 'solverforge-py'
        time_limit: Maximum solve time in seconds


    Returns:
        A function that takes a Instance and returns a Solution
    """

    if method not in AVAILABLE_METHODS:
        raise ValueError(
            f"Unknown method '{method}'. Available: {', '.join(AVAILABLE_METHODS)}"
        )

    if method == "rustvrp":
        return _load_rustvrp()

    if method == "timefold":
        return _load_timefold()

    if method == "solverforge":
        return _load_solverforge()

    if method == "solverforge-py":
        return _load_solverforge_py()

    solvers: dict[str, SolverFn] = {
        "pyvrp": solve_with_pyvrp,
        "ortools": solve_with_ortools,
        "vroom": solve_with_vroom,
        "pyhygese": solve_with_pyhygese,
    }

    return solvers[method]
