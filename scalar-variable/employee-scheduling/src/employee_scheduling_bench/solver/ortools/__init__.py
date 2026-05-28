import json
import subprocess
import sys
from pathlib import Path

from employee_scheduling_bench.domain.models import Assignment, Instance, Solution
from employee_scheduling_bench.solver.instance_json import serialize_instance
from solverforge_bench.fair_start import (
    FairStartViolationError,
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
    witness_from_native_output,
)
from solverforge_bench.model import (
    FairStartWitness,
    NoSolutionFoundError,
    SolverResult,
)

_BINARY_PATH = Path(__file__).parent / "target" / "employee_scheduling_ortools"
_NO_SOLUTION_MESSAGE = "OR-Tools CP-SAT found no feasible solution"


def solve_with_ortools(instance: Instance, time_limit: int) -> SolverResult:
    instance_json = serialize_instance(instance)
    witness = make_fair_start_witness(
        benchmark_name="employee-scheduling",
        solver="ortools",
        planning_state="external_solver_model",
        solver_input=instance_json,
    )
    emit_fair_start_witness(witness)
    if not _BINARY_PATH.exists():
        raise RuntimeError(
            "native OR-Tools solver is not built; run "
            "`make build-employee-scheduling-ortools`"
        )

    result = subprocess.run(
        [str(_BINARY_PATH), str(time_limit)],
        input=instance_json.encode(),
        capture_output=True,
    )
    stderr = result.stderr.decode()
    if result.returncode != 0:
        _, witness = _parse_native_output(result.stdout, instance_json)
        emit_fair_start_witness(witness)
        if stderr.strip() == _NO_SOLUTION_MESSAGE:
            raise NoSolutionFoundError(_NO_SOLUTION_MESSAGE)
        raise RuntimeError(
            f"native OR-Tools solver failed (exit {result.returncode}):\n{stderr}"
        )
    if stderr:
        print(stderr, file=sys.stderr, end="")

    output, witness = _parse_native_output(result.stdout, instance_json)
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
    return solver_result(
        Solution(
            assignments=weekly,
            cost=objective,
            reported_cost=objective,
            fresh_cost=objective,
            score_delta=0 if objective is not None else None,
            score_drift=False if objective is not None else None,
        ),
        witness,
    )


def _parse_native_output(
    stdout: bytes, instance_json: str
) -> tuple[dict[str, object], FairStartWitness]:
    if not stdout:
        raise FairStartViolationError(
            "ortools native output did not include 'fair_start_witness'"
        )
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise FairStartViolationError(
            f"ortools native output was not valid JSON: {exc}"
        ) from exc
    witness = witness_from_native_output(
        output,
        benchmark_name="employee-scheduling",
        solver="ortools",
        planning_state="external_solver_model",
        solver_input=instance_json,
    )
    return output, witness
