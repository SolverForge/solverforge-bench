import json
import subprocess
import sys
from pathlib import Path

from hospital_scale_bench.domain.models import Instance
from hospital_scale_bench.solver.instance_json import serialize_instance
from hospital_scale_bench.solver.output import solution_from_native
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

_BINARY_PATH = Path(__file__).parent / "target" / "hospital_scale_ortools"
BENCHMARK_NAME = "hospital-scale"
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
        benchmark_name=BENCHMARK_NAME,
        solver="ortools",
        planning_state="external_solver_model",
        solver_input=instance_json,
    )
    emit_fair_start_witness(witness)
    if not _BINARY_PATH.exists():
        raise RuntimeError(
            "native OR-Tools solver is not built; run `make build-hospital-scale-ortools`"
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
            _raise_native_failure(output, returncode=result.returncode, stderr=stderr)
        raise SolverExecutionError(
            _native_process_error(result.returncode, stderr),
            native_fields={"native_solver_status": "PROCESS_ERROR"},
        )
    if stderr:
        print(stderr, file=sys.stderr, end="")

    output, witness = _parse_native_output(result.stdout, instance_json)
    solver_metadata = _native_fields(output)
    if solver_metadata.get("native_solver_status") not in {"FEASIBLE", "OPTIMAL"}:
        raise SolverExecutionError(
            "native OR-Tools solver exited successfully without a feasible status",
            native_fields=solver_metadata,
        )
    return solver_result(
        solution_from_native(
            instance,
            output,
            solver_label="OR-Tools",
            solver_metadata=solver_metadata,
        ),
        witness,
    )


def _parse_native_output(
    stdout: bytes, instance_json: str
) -> tuple[dict[str, object], FairStartWitness]:
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise FairStartViolationError(
            f"ortools native output was not valid JSON: {exc}"
        ) from exc
    witness = witness_from_native_output(
        output,
        benchmark_name=BENCHMARK_NAME,
        solver="ortools",
        planning_state="external_solver_model",
        solver_input=instance_json,
    )
    return output, witness


def _raise_native_failure(
    output: dict[str, object], *, returncode: int, stderr: str
) -> None:
    native_fields = _native_fields(output)
    classification = _STATUS_OUTCOMES.get(
        str(native_fields.get("native_solver_status", ""))
    )
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
        if key not in {"assignments", "fair_start_witness"}
    }


def _native_process_error(returncode: int, stderr: str) -> str:
    detail = stderr.strip() or "no stderr output"
    return f"native OR-Tools solver failed (exit {returncode}): {detail}"
