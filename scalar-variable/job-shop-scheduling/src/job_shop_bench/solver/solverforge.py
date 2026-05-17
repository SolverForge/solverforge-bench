from __future__ import annotations

import json
import os
from pathlib import Path

import solverforge_jssp

from job_shop_bench.domain.models import (
    JobShopInstance,
    ScheduledOperation,
    Solution,
)
from job_shop_bench.solver.instance_json import serialize_instance

SOLVERFORGE_CRATE_DIR = Path(__file__).resolve().parent / "solverforge_jssp"


def solve_with_solverforge(instance: JobShopInstance, time_limit: int) -> Solution:
    instance_json = serialize_instance(instance)

    prev_cwd = os.getcwd()
    os.chdir(SOLVERFORGE_CRATE_DIR)
    try:
        result_json = solverforge_jssp.solve_jssp(instance_json, time_limit)
    finally:
        os.chdir(prev_cwd)

    output = json.loads(result_json)
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
