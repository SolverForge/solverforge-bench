import json
import subprocess
import sys
from pathlib import Path

from employee_scheduling_bench.domain.models import Assignment, Instance, Solution
from employee_scheduling_bench.solver.instance_json import serialize_instance

_JAR_PATH = Path(__file__).parent / "timefold" / "target" / "timefold-nrp.jar"


def solve_with_timefold(instance: Instance, time_limit: int) -> Solution:
    result = subprocess.run(
        ["java", "-jar", str(_JAR_PATH), str(time_limit)],
        input=serialize_instance(instance).encode(),
        capture_output=True,
    )
    stderr = result.stderr.decode()
    if result.returncode != 0:
        raise RuntimeError(
            f"timefold solver failed (exit {result.returncode}):\n" f"{stderr}"
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

    return Solution(
        assignments=weekly,
        cost=output["cost"],
        reported_cost=output["cost"],
        fresh_cost=output["cost"],
        score_delta=0,
        score_drift=False,
    )
