import os
from pathlib import Path

import solverforge_nrp

from employee_scheduling_bench.domain.models import Instance, Solution, Assignment
from employee_scheduling_bench.solver.instance_json import serialize_instance

SOLVERFORGE_CRATE_DIR = Path(__file__).resolve().parent / "solverforge_nrp"

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def solve_with_solverforge(instance: Instance, time_limit: int) -> Solution:
    instance_json = serialize_instance(instance)

    prev_cwd = os.getcwd()
    os.chdir(SOLVERFORGE_CRATE_DIR)
    try:
        result_json = solverforge_nrp.solve_nrp(instance_json, time_limit)
    finally:
        os.chdir(prev_cwd)

    import json

    result = json.loads(result_json)
    solver_metadata = {
        key: value for key, value in result.items() if key != "assignments"
    }
    hard_violations = result.get("hard_violations", 0)
    if hard_violations:
        raise RuntimeError(
            f"SolverForge returned no hard-feasible solution: {hard_violations} hard violations"
        )

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

    return Solution(
        assignments=weekly,
        cost=result.get("fresh_cost", result["cost"]),
        reported_cost=result.get("reported_cost"),
        fresh_cost=result.get("fresh_cost"),
        score_delta=result.get("score_delta"),
        score_drift=result.get("score_drift"),
        reported_score=result.get("reported_score"),
        fresh_score=result.get("fresh_score"),
        solver_metadata=solver_metadata,
    )
