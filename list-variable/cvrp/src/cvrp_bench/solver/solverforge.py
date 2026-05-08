import json

import solverforge_cvrp

from cvrp_bench.domain.models import Instance, Solution


def solve_with_solverforge(instance: Instance, time_limit: int) -> Solution:
    """
    Solve the CVRP using the SolverForge 0.8.6 retained list-variable runtime.

    The Rust crate keeps the benchmark-facing contract thin:
      - Hard: every customer must be assigned exactly once and every route must
        respect vehicle capacity
      - Soft: minimise total rounded travel distance

    Search policy lives in the embedded `solver.toml`, and the Python-provided
    time limit is applied through the model's config provider.
    """
    # 1 transform: build input matching the Rust InstanceInput struct.
    # distance_matrix is pre-rounded to match round(instance.edge_weight[i][j])
    # as used by every other solver (pyvrp, ortools, vroom, pyhygese, timefold_java).
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
    result_json = solverforge_cvrp.solve_cvrp(instance_json, time_limit)

    # 3 transform: routes are already depot-excluded lists of customer indices
    result = json.loads(result_json)
    return Solution(routes=result["routes"], cost=result["cost"])
