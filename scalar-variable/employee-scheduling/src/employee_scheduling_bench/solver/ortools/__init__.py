import json
import subprocess
import sys
from pathlib import Path

from employee_scheduling_bench.domain.models import Assignment, Instance, Solution
from employee_scheduling_bench.solver.instance_json import serialize_instance

_BINARY_PATH = Path(__file__).parent / "target" / "employee_scheduling_ortools"


def solve_with_ortools(instance: Instance, time_limit: int) -> Solution:
    if not _BINARY_PATH.exists():
        raise RuntimeError(
            "native OR-Tools solver is not built; run "
            "`make build-employee-scheduling-ortools`"
        )

    result = subprocess.run(
        [str(_BINARY_PATH), str(time_limit)],
        input=serialize_instance(instance).encode(),
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
    weekly: list[list[Assignment]] = []
    for week_assignments in output["assignments"]:
        weekly.append(
            [
                Assignment(
                    nurse=a["nurse"],
                    day=a["day"],
                    shiftType=a["shiftType"],
                    skill=a["skill"],
                )
                for a in week_assignments
            ]
        )

    objective = output.get("objective")
    return Solution(
        assignments=weekly,
        cost=objective,
        reported_cost=objective,
        fresh_cost=objective,
        score_delta=0 if objective is not None else None,
        score_drift=False if objective is not None else None,
    )
