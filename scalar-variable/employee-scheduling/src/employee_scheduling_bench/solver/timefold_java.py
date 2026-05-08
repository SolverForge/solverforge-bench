import json
import subprocess
from pathlib import Path

from employee_scheduling_bench.domain.models import Assignment, Instance, Solution
from employee_scheduling_bench.solver.instance_json import serialize_instance

_JAR_PATH = Path(__file__).parent / "timefold_java" / "target" / "timefold-nrp.jar"


def _wall_timeout_seconds(time_limit: int) -> int:
    return int(time_limit + 5)


def solve_with_timefold_java(instance: Instance, time_limit: int) -> Solution:
    result = subprocess.run(
        ["java", "-jar", str(_JAR_PATH), str(time_limit)],
        input=serialize_instance(instance).encode(),
        capture_output=True,
        timeout=_wall_timeout_seconds(time_limit),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"timefold_java solver failed (exit {result.returncode}):\n"
            f"{result.stderr.decode()}"
        )

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

    return Solution(assignments=weekly, cost=output["cost"])
