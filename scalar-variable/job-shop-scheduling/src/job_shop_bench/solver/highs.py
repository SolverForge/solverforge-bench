from __future__ import annotations

import math
from typing import Any

import highspy
import numpy as np

from job_shop_bench.domain.models import JobShopInstance, ScheduledOperation, Solution
from job_shop_bench.solver.instance_json import serialize_instance
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import (
    NoSolutionFoundError,
    SolverExecutionError,
    SolverResult,
)


def _status_name(h: highspy.Highs) -> str:
    return str(h.modelStatusToString(h.getModelStatus()))


def _native_fields(h: highspy.Highs, num_cols: int, num_rows: int) -> dict[str, Any]:
    info = h.getInfo()
    return {
        "native_solver_status": _status_name(h),
        "highs_mip_gap": float(info.mip_gap) if math.isfinite(info.mip_gap) else None,
        "highs_mip_node_count": int(info.mip_node_count),
        "highs_model_variables": num_cols,
        "highs_model_rows": num_rows,
    }


def solve_with_highs(instance: JobShopInstance, time_limit: int) -> SolverResult:
    """
    HiGHS (highspy) JSSP adapter: the mainline C++ HiGHS core through its
    published Python wheel, encoding the same disjunctive MILP as the OR-Tools
    CP-SAT adapter (per-operation integer starts inside a duration-sum horizon,
    job precedence, pairwise machine disjunctions, makespan minimization) from
    zero starts.
    """
    witness = make_fair_start_witness(
        benchmark_name="job-shop-scheduling",
        solver="highs",
        planning_state="external_solver_model",
        solver_input=serialize_instance(instance),
    )
    emit_fair_start_witness(witness)

    ops = [op for job in instance.operations_by_job for op in job]
    if not ops:
        raise SolverExecutionError("HiGHS JSSP instance has no operations")
    max_duration = max(op.duration for op in ops)
    horizon = max(1, sum(op.duration for op in ops))
    big_m = horizon + max_duration
    num_ops = len(ops)
    num_machines = instance.num_machines
    by_machine: dict[int, list[int]] = {}
    for index, op in enumerate(ops):
        by_machine.setdefault(op.machine_id, []).append(index)

    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("log_to_console", False)
    h.setOptionValue("threads", 1)
    h.setOptionValue("random_seed", 1)
    h.setOptionValue("time_limit", float(max(0.1, time_limit)))

    # Columns: one integer start per operation, then one binary per unordered
    # operation pair that shares a machine, then one makespan variable.
    num_pairs = sum(len(group) * (len(group) - 1) // 2 for group in by_machine.values())
    num_cols = num_ops + num_pairs + 1
    lower = np.zeros(num_cols, dtype=np.float64)
    upper = np.empty(num_cols, dtype=np.float64)
    upper[:num_ops] = horizon
    upper[num_ops : num_ops + num_pairs] = 1.0
    upper[-1] = horizon
    costs = np.zeros(num_cols, dtype=np.float64)
    costs[-1] = 1.0
    h.addCols(
        num_cols,
        costs,
        lower,
        upper,
        0,
        np.array([], dtype=np.int32),
        np.array([], dtype=np.int32),
        np.array([], dtype=np.float64),
    )
    integrality = np.full(num_cols, highspy.HighsVarType.kInteger, dtype=np.uint8)
    h.changeColsIntegrality(num_cols, np.arange(num_cols, dtype=np.int32), integrality)

    makespan_col = num_cols - 1
    rows_lower: list[float] = []
    rows_upper: list[float] = []
    row_starts: list[int] = []
    row_indices: list[int] = []
    row_values: list[float] = []

    def add_row(
        entries: list[tuple[int, float]], lower_b: float, upper_b: float
    ) -> None:
        row_starts.append(len(row_indices))
        rows_lower.append(lower_b)
        rows_upper.append(upper_b)
        for col, coef in entries:
            row_indices.append(col)
            row_values.append(coef)

    # One binary per unordered operation pair that shares a machine.
    pair_cursor = num_ops
    for machine in range(num_machines):
        group = by_machine.get(machine, [])
        for a_pos in range(len(group)):
            for b_pos in range(a_pos + 1, len(group)):
                a, b = group[a_pos], group[b_pos]
                op_a, op_b = ops[a], ops[b]
                # y=0: s_a - s_b >= d_b (b starts no earlier than a's end).
                add_row(
                    [(a, 1.0), (b, -1.0), (pair_cursor, float(big_m))],
                    float(op_b.duration),
                    highspy.kHighsInf,
                )
                # y=1: s_b - s_a >= d_a (a starts no earlier than b's end).
                add_row(
                    [(b, 1.0), (a, -1.0), (pair_cursor, -float(big_m))],
                    float(op_a.duration) - big_m,
                    highspy.kHighsInf,
                )
                pair_cursor += 1

    # Job precedence chains: the flattened op order keeps each job's ops
    # consecutive, so chain membership is index arithmetic, not a lookup.
    flat_index = 0
    for job in instance.operations_by_job:
        for prev_pos, cur_pos in zip(
            range(flat_index, flat_index + len(job) - 1),
            range(flat_index + 1, flat_index + len(job)),
        ):
            add_row(
                [(cur_pos, 1.0), (prev_pos, -1.0)],
                float(ops[prev_pos].duration),
                highspy.kHighsInf,
            )
        flat_index += len(job)

    # Makespan >= every operation end.
    for index, op in enumerate(ops):
        add_row(
            [(makespan_col, 1.0), (index, -1.0)],
            float(op.duration),
            highspy.kHighsInf,
        )

    h.addRows(
        len(rows_lower),
        np.array(rows_lower, dtype=np.float64),
        np.array(rows_upper, dtype=np.float64),
        len(row_indices),
        np.array(row_starts, dtype=np.int32),
        np.array(row_indices, dtype=np.int32),
        np.array(row_values, dtype=np.float64),
    )

    h.run()
    model_status = h.getModelStatus()
    solution = h.getSolution()
    if model_status == highspy.HighsModelStatus.kInfeasible:
        raise NoSolutionFoundError(
            "HiGHS proved the JSSP model infeasible",
            termination_status="proved_infeasible",
            native_fields=_native_fields(h, num_cols, len(rows_lower)),
        )
    if model_status != highspy.HighsModelStatus.kOptimal and not solution.value_valid:
        raise NoSolutionFoundError(
            "HiGHS returned no JSSP incumbent before the time limit",
            termination_status="no_incumbent",
            native_fields=_native_fields(h, num_cols, len(rows_lower)),
        )

    values = solution.col_value
    operations = tuple(
        ScheduledOperation(
            job_id=op.job_id,
            op_index=op.op_index,
            machine_id=op.machine_id,
            start=int(round(values[index])),
            duration=op.duration,
        )
        for index, op in enumerate(ops)
    )
    reported = int(round(values[makespan_col]))
    return solver_result(
        Solution(operations=operations, reported_makespan=reported), witness
    )
