import json
import os
from pathlib import Path

import solverforge_hospital_scale

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
from solverforge_bench.solverforge_failures import classify_solverforge_failure

SOLVERFORGE_CRATE_DIR = Path(__file__).resolve().parent / "solverforge_hospital"
BENCHMARK_NAME = "hospital-scale"


def solve_with_solverforge(instance: Instance, time_limit: int) -> SolverResult:
    instance_json = serialize_instance(instance)
    witness = make_fair_start_witness(
        benchmark_name=BENCHMARK_NAME,
        solver="solverforge",
        planning_state="unassigned_scalar_variables",
        solver_input=instance_json,
    )

    prev_cwd = os.getcwd()
    os.chdir(SOLVERFORGE_CRATE_DIR)
    try:
        emit_fair_start_witness(witness)
        try:
            result_json = solverforge_hospital_scale.solve_hospital(
                instance_json, time_limit
            )
        except Exception as exc:
            classified = classify_solverforge_failure(
                exc,
                solver_name="SolverForge Rust",
            )
            if classified is not None:
                raise classified from exc
            raise
    finally:
        os.chdir(prev_cwd)

    result = json.loads(result_json)
    witness = witness_from_native_output(
        result,
        benchmark_name=BENCHMARK_NAME,
        solver="solverforge",
        planning_state="unassigned_scalar_variables",
        solver_input=instance_json,
    )
    solver_metadata = {
        key: value
        for key, value in result.items()
        if key not in {"assignments", "fair_start_witness"}
    }
    return solver_result(
        solution_from_native(
            instance,
            result,
            solver_label="SolverForge Rust",
            solver_metadata=solver_metadata,
        ),
        witness,
    )
