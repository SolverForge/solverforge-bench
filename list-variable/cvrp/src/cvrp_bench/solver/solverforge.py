import json

import solverforge_cvrp

from cvrp_bench.domain.models import Instance, Solution
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
    witness_from_native_output,
)
from solverforge_bench.model import SolverResult


def solve_with_solverforge(instance: Instance, time_limit: int) -> SolverResult:
    """
    Solve the CVRP using the SolverForge 0.15.1 retained list-variable runtime.

    The Rust crate keeps the benchmark-facing contract thin:
      - Hard: every customer must be assigned exactly once and every route must
        respect vehicle capacity
      - Soft: minimise total rounded travel distance

    Search policy lives in the embedded `solver.toml`, and the Python-provided
    time limit is applied through the model's config provider.
    """
    # 1 transform: build input matching the Rust InstanceInput struct.
    # distance_matrix is pre-rounded to match round(instance.edge_weight[i][j])
    # as used by every other solver (pyvrp, ortools, vroom, pyhygese, timefold).
    instance_json = json.dumps(
        {
            "dimension": instance.dimension,
            "capacity": instance.capacity,
            "demand": instance.demand.tolist(),
            "depot": int(instance.depot[0]),
            "distance_matrix": instance.edge_weight.round().astype(int).tolist(),
        }
    )

    # 2 solve
    witness = make_fair_start_witness(
        benchmark_name="cvrp",
        solver="solverforge",
        planning_state="empty_list_variables",
        solver_input=instance_json,
    )
    emit_fair_start_witness(witness)
    result_json = solverforge_cvrp.solve_cvrp(instance_json, time_limit)

    # 3 transform: routes are already depot-excluded lists of customer indices
    result = json.loads(result_json)
    witness = witness_from_native_output(
        result,
        benchmark_name="cvrp",
        solver="solverforge",
        planning_state="empty_list_variables",
        solver_input=instance_json,
    )
    return solver_result(
        Solution(routes=result["routes"], cost=result["cost"]), witness
    )
