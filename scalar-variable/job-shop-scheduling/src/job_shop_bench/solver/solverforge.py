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
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
    witness_from_native_output,
)
from solverforge_bench.model import SolverResult

SOLVERFORGE_CRATE_DIR = Path(__file__).resolve().parent / "solverforge_jssp"


def solve_with_solverforge(instance: JobShopInstance, time_limit: int) -> SolverResult:
    instance_json = serialize_instance(instance)
    witness = make_fair_start_witness(
        benchmark_name="job-shop-scheduling",
        solver="solverforge",
        planning_state="empty_list_variables",
        solver_input=instance_json,
    )

    prev_cwd = os.getcwd()
    os.chdir(SOLVERFORGE_CRATE_DIR)
    try:
        emit_fair_start_witness(witness)
        result_json = solverforge_jssp.solve_jssp(instance_json, time_limit)
    finally:
        os.chdir(prev_cwd)

    output = json.loads(result_json)
    witness = witness_from_native_output(
        output,
        benchmark_name="job-shop-scheduling",
        solver="solverforge",
        planning_state="empty_list_variables",
        solver_input=instance_json,
    )
    return solver_result(
        Solution(
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
        ),
        witness,
    )
