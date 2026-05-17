from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from job_shop_bench.domain.models import (
    JobShopInstance,
    ScheduledOperation,
    Solution,
)
from job_shop_bench.solver.instance_json import serialize_instance

_JAR_PATH = Path(__file__).parent / "timefold" / "target" / "timefold-jssp.jar"


def solve_with_timefold(instance: JobShopInstance, time_limit: int) -> Solution:
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
    return Solution(
        operations=[
            ScheduledOperation(
                job_id=op["job_id"],
                op_index=op["op_index"],
                machine_id=op["machine_id"],
                start=op["start"],
                duration=op["duration"],
            )
            for op in output["operations"]
        ],
        reported_makespan=output["reported_makespan"],
    )
