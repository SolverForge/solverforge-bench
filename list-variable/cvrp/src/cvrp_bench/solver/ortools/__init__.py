import json
import subprocess
import sys
from pathlib import Path

from cvrp_bench.domain.models import Instance, Solution

_BINARY_PATH = Path(__file__).parent / "target" / "cvrp_ortools"


def solve_with_ortools(instance: Instance, time_limit: int) -> Solution:
    if not _BINARY_PATH.exists():
        raise RuntimeError(
            "native OR-Tools solver is not built; run `make build-cvrp-ortools`"
        )

    payload = {
        "capacity": int(instance.capacity),
        "demand": [int(value) for value in instance.demand.tolist()],
        "edge_weight": [
            [round(float(value)) for value in row]
            for row in instance.edge_weight.tolist()
        ],
    }
    result = subprocess.run(
        [str(_BINARY_PATH), str(time_limit)],
        input=json.dumps(payload).encode(),
        capture_output=True,
    )
    stderr = result.stderr.decode()
    if result.returncode != 0:
        raise RuntimeError(
            f"native OR-Tools solver failed (exit {result.returncode}):\n{stderr}"
        )
    if stderr:
        print(stderr, file=sys.stderr, end="")

    output = json.loads(result.stdout)
    return Solution(cost=int(output["cost"]), routes=output["routes"])
