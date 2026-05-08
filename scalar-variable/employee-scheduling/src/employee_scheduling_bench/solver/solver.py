from typing import Callable
from employee_scheduling_bench.domain.models import Instance, Solution
from employee_scheduling_bench.solver.ortools import solve_with_ortools
from employee_scheduling_bench.solver.solverforge import solve_with_solverforge
from employee_scheduling_bench.solver.timefold_java import solve_with_timefold_java

SolverFn = Callable[[Instance, int], Solution]


def create_solver(method: str, *, time_limit: int = 60) -> SolverFn:
    available_methods = ["solverforge", "timefold_java", "ortools"]

    if method not in available_methods:
        raise ValueError(
            f"Unknown method '{method}'. Available: {', '.join(available_methods)}"
        )

    solvers: dict[str, SolverFn] = {
        "solverforge": solve_with_solverforge,
        "timefold_java": solve_with_timefold_java,
        "ortools": solve_with_ortools,
    }

    return solvers[method]
