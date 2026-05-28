import json
import subprocess
import sys
from pathlib import Path

from cvrp_bench.domain.models import Instance, Solution
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import SolverResult

_BINARY_PATH = Path(__file__).parent / "target" / "cvrp_vroom"


def solve_with_vroom(instance: Instance, time_limit: int) -> SolverResult:
    matrix = [
        [round(float(value)) for value in row] for row in instance.edge_weight.tolist()
    ]
    payload = {
        "vehicles": [
            {
                "id": index,
                "start_index": 0,
                "end_index": 0,
                "capacity": [int(instance.capacity)],
            }
            for index, _ in enumerate(instance.demand)
        ],
        "jobs": [
            {
                "id": index,
                "location_index": index,
                "delivery": [int(instance.demand[index])],
            }
            for index in range(1, len(instance.demand))
        ],
        "matrices": {
            "car": {
                "durations": matrix,
                "costs": matrix,
            }
        },
    }
    witness = make_fair_start_witness(
        benchmark_name="cvrp",
        solver="vroom",
        planning_state="external_solver_model",
        solver_input=payload,
    )
    emit_fair_start_witness(witness)
    if not _BINARY_PATH.exists():
        raise RuntimeError(
            "native VROOM solver is not built; run `make build-cvrp-vroom`"
        )

    result = subprocess.run(
        [
            str(_BINARY_PATH),
            "--limit",
            str(time_limit),
            "--threads",
            "1",
            "--explore",
            "5",
        ],
        input=json.dumps(payload).encode(),
        capture_output=True,
    )
    stderr = result.stderr.decode()
    if result.returncode != 0:
        stdout = result.stdout.decode()
        raise RuntimeError(
            f"native VROOM solver failed (exit {result.returncode}):\n"
            f"{stderr}{stdout}"
        )
    if stderr:
        print(stderr, file=sys.stderr, end="")

    output = json.loads(result.stdout)
    if output.get("code") != 0:
        raise RuntimeError(f"native VROOM solver failed: {output}")

    routes = []
    for route in output["routes"]:
        customers = [
            int(step["id"]) for step in route["steps"] if step["type"] == "job"
        ]
        if customers:
            routes.append(customers)

    return solver_result(
        Solution(cost=int(output["summary"]["cost"]), routes=routes),
        witness,
    )
