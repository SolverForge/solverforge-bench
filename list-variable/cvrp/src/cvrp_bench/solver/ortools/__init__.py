import json
import subprocess
import sys
from pathlib import Path

from cvrp_bench.domain.models import Instance, Solution
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
    witness_from_native_output,
)
from solverforge_bench.model import NoSolutionFoundError
from solverforge_bench.model import SolverResult

_BINARY_PATH = Path(__file__).parent / "target" / "cvrp_ortools"
_NO_SOLUTION_MESSAGE = "OR-Tools found no CVRP solution"


def solve_with_ortools(instance: Instance, time_limit: int) -> SolverResult:
    payload = {
        "capacity": int(instance.capacity),
        "demand": [int(value) for value in instance.demand.tolist()],
        "edge_weight": [
            [round(float(value)) for value in row]
            for row in instance.edge_weight.tolist()
        ],
    }
    witness = make_fair_start_witness(
        benchmark_name="cvrp",
        solver="ortools",
        planning_state="external_solver_model",
        solver_input=payload,
    )
    emit_fair_start_witness(witness)
    if not _BINARY_PATH.exists():
        raise RuntimeError(
            "native OR-Tools solver is not built; run `make build-cvrp-ortools`"
        )

    result = subprocess.run(
        [str(_BINARY_PATH), str(time_limit)],
        input=json.dumps(payload).encode(),
        capture_output=True,
    )
    stderr = result.stderr.decode()
    if result.returncode != 0:
        if stderr.strip() == _NO_SOLUTION_MESSAGE:
            raise NoSolutionFoundError(_NO_SOLUTION_MESSAGE)
        raise RuntimeError(
            f"native OR-Tools solver failed (exit {result.returncode}):\n{stderr}"
        )
    if stderr:
        print(stderr, file=sys.stderr, end="")

    output = json.loads(result.stdout)
    witness = witness_from_native_output(
        output,
        benchmark_name="cvrp",
        solver="ortools",
        planning_state="external_solver_model",
        solver_input=payload,
    )
    return solver_result(
        Solution(cost=int(output["cost"]), routes=output["routes"]),
        witness,
    )
