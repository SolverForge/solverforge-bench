from typing import Callable
from cvrp_bench.domain.models import Instance, Solution
from cvrp_bench.solver.ortools import solve_with_ortools
from cvrp_bench.solver.pyhygese import solve_with_pyhygese
from cvrp_bench.solver.pyvrp import solve_with_pyvrp
from cvrp_bench.solver.vroom import solve_with_vroom


AVAILABLE_METHODS = [
    "pyvrp",
    "ortools",
    "vroom",
    "timefold_java",
    "rustvrp",
    "pyhygese",
    "solverforge",
]


def _load_rustvrp():
    from cvrp_bench.solver.rustvrp.rustvrp import solve_with_rustvrp

    return solve_with_rustvrp


def _load_timefold_java():
    from cvrp_bench.solver.timefold_java import solve_with_timefold_java

    return solve_with_timefold_java


def _load_solverforge():
    from cvrp_bench.solver.solverforge import solve_with_solverforge

    return solve_with_solverforge


# Type alias for solver functions
SolverFn = Callable[[Instance, int], Solution]


def create_solver(method: str, *, time_limit: int = 60) -> SolverFn:
    """
    Factory function that returns a configured solver function.

    Args:
        method: One of 'pyvrp', 'ortools', 'vroom', 'timefold_java', 'rustvrp',
            'pyhygese', 'solverforge'
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

    if method == "timefold_java":
        return _load_timefold_java()

    if method == "solverforge":
        return _load_solverforge()

    solvers: dict[str, SolverFn] = {
        "pyvrp": solve_with_pyvrp,
        "ortools": solve_with_ortools,
        "vroom": solve_with_vroom,
        "pyhygese": solve_with_pyhygese,
    }

    return solvers[method]
