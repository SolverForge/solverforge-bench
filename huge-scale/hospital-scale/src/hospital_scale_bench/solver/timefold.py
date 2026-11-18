import json
import subprocess
import sys
from pathlib import Path

from hospital_scale_bench.domain.models import Instance
from hospital_scale_bench.solver.instance_json import serialize_instance
from hospital_scale_bench.solver.output import solution_from_native
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
    witness_from_native_output,
)
from solverforge_bench.model import SolverResult

_JAR_PATH = (
    Path(__file__).parent / "timefold" / "target" / "timefold-hospital-scale.jar"
)
BENCHMARK_NAME = "hospital-scale"


def solve_with_timefold(instance: Instance, time_limit: int) -> SolverResult:
    instance_json = serialize_instance(instance)
    witness = make_fair_start_witness(
        benchmark_name=BENCHMARK_NAME,
        solver="timefold",
        planning_state="unassigned_scalar_variables",
        solver_input=instance_json,
    )
    emit_fair_start_witness(witness)
    result = subprocess.run(
        ["java", "-jar", str(_JAR_PATH), str(time_limit)],
        input=instance_json.encode(),
        capture_output=True,
    )
    stderr = result.stderr.decode()
    if result.returncode != 0:
        raise RuntimeError(
            f"timefold solver failed (exit {result.returncode}):\n{stderr}"
        )
    if stderr:
        print(stderr, file=sys.stderr, end="")

    output = json.loads(result.stdout)
    witness = witness_from_native_output(
        output,
        benchmark_name=BENCHMARK_NAME,
        solver="timefold",
        planning_state="unassigned_scalar_variables",
        solver_input=instance_json,
    )
    solver_metadata = {
        key: value
        for key, value in output.items()
        if key not in {"assignments", "fair_start_witness"}
    }
    return solver_result(
        solution_from_native(
            instance,
            output,
            solver_label="Timefold",
            solver_metadata=solver_metadata,
        ),
        witness,
    )
