from cvrp_bench.domain.models import Instance, Solution
import hygese as hgs
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import SolverResult


def solve_with_pyhygese(instance: Instance, time_limit: int) -> SolverResult:
    # Simple pyhygese baseline would go here

    data = dict()
    data["distance_matrix"] = instance.edge_weight.round()
    data["num_vehicles"] = len(instance.demand) - 1
    data["depot"] = instance.depot[0]
    data["demands"] = instance.demand
    data["vehicle_capacity"] = instance.capacity
    data["service_times"] = [0 for _ in instance.demand]

    # Solver initialization
    ap = hgs.AlgorithmParameters(timeLimit=time_limit)  # seconds
    hgs_solver = hgs.Solver(parameters=ap, verbose=True)

    # Solve
    witness = make_fair_start_witness(
        benchmark_name="cvrp",
        solver="pyhygese",
        planning_state="external_solver_model",
        solver_input=data,
    )
    emit_fair_start_witness(witness)
    result = hgs_solver.solve_cvrp(data)
    return solver_result(Solution(routes=result.routes, cost=result.cost), witness)
