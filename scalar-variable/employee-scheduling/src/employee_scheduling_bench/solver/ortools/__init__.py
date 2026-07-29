import json
import subprocess
import sys
from pathlib import Path

from employee_scheduling_bench.domain.models import Assignment, Instance, Solution
from employee_scheduling_bench.solver.instance_json import serialize_instance
from employee_scheduling_bench.validation import validate
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
    SolverExecutionError,
    SolverResult,
)

_BINARY_PATH = Path(__file__).parent / "target" / "employee_scheduling_ortools"
_STATUS_OUTCOMES = {
    "UNKNOWN": (
        NoSolutionFoundError,
        "no_incumbent",
        "OR-Tools CP-SAT returned no incumbent before the time limit",
    ),
    "INFEASIBLE": (
        NoSolutionFoundError,
        "proved_infeasible",
        "OR-Tools CP-SAT proved the model infeasible",
    ),
    "MODEL_INVALID": (
        SolverExecutionError,
        "model_invalid",
        "OR-Tools CP-SAT rejected the model as invalid",
    ),
}


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
        if result.stdout:
            output, witness = _parse_native_output(result.stdout, instance_json)
            emit_fair_start_witness(witness)
            _raise_native_failure(
                output,
                returncode=result.returncode,
                stderr=stderr,
            )
        raise SolverExecutionError(
            _native_process_error(result.returncode, stderr),
            native_fields={"native_solver_status": "PROCESS_ERROR"},
        )
    if stderr:
        print(stderr, file=sys.stderr, end="")

    output, witness = _parse_native_output(result.stdout, instance_json)
    native_fields = _native_fields(output)
    native_status = native_fields.get("native_solver_status")
    if native_status not in {"FEASIBLE", "OPTIMAL"}:
        raise SolverExecutionError(
            "native OR-Tools solver exited successfully without a feasible status",
            native_fields=native_fields,
        )
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
    solution = Solution(
        assignments=weekly,
        reported_cost=objective,
        solver_metadata=native_fields,
    )
    _apply_fresh_score(solution, instance=instance)
    return solver_result(
        solution,
        witness,
    )


def _apply_fresh_score(solution: Solution, *, instance: Instance) -> None:
    fresh_cost = validate(solution=solution, instance=instance)
    solution.cost = fresh_cost
    solution.fresh_cost = fresh_cost
    solution.score_delta = (
        solution.reported_cost - fresh_cost
        if solution.reported_cost is not None
        else None
    )
    solution.score_drift = (
        solution.reported_cost != fresh_cost
        if solution.reported_cost is not None
        else None
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


def _raise_native_failure(
    output: dict[str, object],
    *,
    returncode: int,
    stderr: str,
) -> None:
    native_fields = _native_fields(output)
    native_status = str(native_fields.get("native_solver_status", ""))
    classification = _STATUS_OUTCOMES.get(native_status)
    if classification is not None:
        error_type, termination_status, message = classification
        raise error_type(
            message,
            termination_status=termination_status,
            native_fields=native_fields,
        )
    raise SolverExecutionError(
        _native_process_error(returncode, stderr),
        native_fields=native_fields,
    )


def _native_fields(output: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in output.items()
        if key not in {"assignments", "fair_start_witness", "objective"}
    }


def _native_process_error(returncode: int, stderr: str) -> str:
    detail = stderr.strip() or "no stderr output"
    return f"native OR-Tools solver failed (exit {returncode}): {detail}"
