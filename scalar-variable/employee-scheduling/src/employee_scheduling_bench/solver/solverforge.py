import os
from pathlib import Path

import solverforge_nrp

from employee_scheduling_bench.domain.models import Instance, Solution, Assignment
from employee_scheduling_bench.solver.instance_json import serialize_instance
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
    witness_from_native_output,
)
from solverforge_bench.model import SolverResult

SOLVERFORGE_CRATE_DIR = Path(__file__).resolve().parent / "solverforge_nrp"

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def solve_with_solverforge(instance: Instance, time_limit: int) -> SolverResult:
    instance_json = serialize_instance(instance)
    witness = make_fair_start_witness(
        benchmark_name="employee-scheduling",
        solver="solverforge",
        planning_state="unassigned_scalar_variables",
        solver_input=instance_json,
    )

    prev_cwd = os.getcwd()
    os.chdir(SOLVERFORGE_CRATE_DIR)
    try:
        emit_fair_start_witness(witness)
        result_json = solverforge_nrp.solve_nrp(instance_json, time_limit)
    finally:
        os.chdir(prev_cwd)

    import json

    result = json.loads(result_json)
    witness = witness_from_native_output(
        result,
        benchmark_name="employee-scheduling",
        solver="solverforge",
        planning_state="unassigned_scalar_variables",
        solver_input=instance_json,
    )
    solver_metadata = {
        key: value
        for key, value in result.items()
        if key not in {"assignments", "fair_start_witness"}
    }
    weekly = []
    for week_assignments in result["assignments"]:
        week = []
        for a in week_assignments:
            week.append(
                Assignment(
                    nurse=a["nurse"],
                    day=a["day"],
                    shiftType=a["shiftType"],
                    skill=a["skill"],
                )
            )
        weekly.append(week)

    return solver_result(
        Solution(
            assignments=weekly,
            cost=result.get("fresh_cost", result["cost"]),
            reported_cost=result.get("reported_cost"),
            fresh_cost=result.get("fresh_cost"),
            score_delta=result.get("score_delta"),
            score_drift=result.get("score_drift"),
            reported_score=result.get("reported_score"),
            fresh_score=result.get("fresh_score"),
            solver_metadata=solver_metadata,
        ),
        witness,
    )
