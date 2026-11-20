import json
import subprocess
import sys
from pathlib import Path

from delivery_scale_bench.domain.models import Instance
from delivery_scale_bench.solver.instance_json import serialize_instance
from delivery_scale_bench.solver.output import solution_from_native
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
    witness_from_native_output,
)
from solverforge_bench.model import NoSolutionFoundError, SolverResult

_BINARY_PATH = Path(__file__).parent / "target" / "delivery_scale_ortools"
_NO_SOLUTION_MESSAGE = "OR-Tools found no delivery-scale solution"
BENCHMARK_NAME = "delivery-scale"


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
            "native OR-Tools solver is not built; run `make build-delivery-scale-ortools`"
        )

    result = subprocess.run(
        [str(_BINARY_PATH), str(time_limit)],
        input=instance_json.encode(),
        capture_output=True,
    )
    stderr = result.stderr.decode()
    if result.returncode != 0:
        if stderr.strip() == _NO_SOLUTION_MESSAGE:
            raise NoSolutionFoundError(_NO_SOLUTION_MESSAGE)
        raise RuntimeError(
            f"native OR-Tools solver failed (exit {result.returncode}):\n{stderr}"
        )
    if stderr:
        print(stderr, file=sys.stderr, end="")

    output = json.loads(result.stdout)
    witness = witness_from_native_output(
        output,
        benchmark_name=BENCHMARK_NAME,
        solver="ortools",
        planning_state="external_solver_model",
        solver_input=instance_json,
    )
    solver_metadata = {
        key: value
        for key, value in output.items()
        if key not in {"routes", "fair_start_witness"}
    }
    return solver_result(
        solution_from_native(
            instance,
            output,
            solver_label="OR-Tools",
            solver_metadata=solver_metadata,
        ),
        witness,
    )
