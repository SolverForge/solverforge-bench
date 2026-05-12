"""Shared benchmark run matrix and row construction."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import Any

from solverforge_bench.csv import GLOBAL_COLUMNS, IncrementalCsvWriter
from solverforge_bench.execution import run_solver, watchdog_limit_seconds
from solverforge_bench.model import BenchmarkRow, BenchmarkSpec, Evaluation
from solverforge_bench.postgres import PostgresResultWriter, make_postgres_config


def run_benchmark(spec: BenchmarkSpec, args: Any) -> Path:
    run_stamp = getattr(args, "run_stamp")
    output_path = (
        Path(args.output) if args.output else spec.output_path(args, run_stamp)
    )
    artifact_dir = spec.artifact_dir(args, run_stamp)
    solvers = args.solver or spec.default_solvers
    time_limits = args.time_limits or spec.default_time_limits

    postgres_writer = None
    with ExitStack() as stack:
        writer = stack.enter_context(
            IncrementalCsvWriter(
                output_path, columns=_ordered_columns(spec.native_columns)
            )
        )
        if args.save_postgres:
            postgres_writer = stack.enter_context(
                PostgresResultWriter(
                    make_postgres_config(
                        args=args,
                        spec=spec,
                        output_path=output_path,
                        artifact_dir=artifact_dir,
                        solvers=solvers,
                        time_limits=time_limits,
                    )
                )
            )
            args.postgres_run_id = str(postgres_writer.run_id)

        for case in spec.cases(args):
            for time_limit in time_limits:
                watchdog_seconds = watchdog_limit_seconds(
                    time_limit,
                    multiplier=args.watchdog_multiplier,
                    grace_seconds=args.watchdog_grace_seconds,
                )
                for solver_name in solvers:
                    run = run_solver(
                        solver_name=solver_name,
                        solver_factory=spec.create_solver,
                        solution_model=spec.solution_model,
                        instance=case.payload,
                        time_limit_seconds=time_limit,
                        watchdog_seconds=watchdog_seconds,
                    )
                    evaluation = _evaluate(
                        spec,
                        case=case,
                        run=run,
                        artifact_dir=artifact_dir,
                    )
                    row = _row(
                        spec=spec,
                        case=case,
                        run=run,
                        evaluation=evaluation,
                        wall_time_tolerance=args.wall_time_tolerance,
                    )
                    writer.write_row(row.as_dict())
                    if postgres_writer is not None:
                        postgres_writer.write_row(row)

    return output_path


def _ordered_columns(native_columns: list[str]) -> list[str]:
    columns = [*GLOBAL_COLUMNS, *native_columns]
    return list(dict.fromkeys(columns))


def _evaluate(spec: BenchmarkSpec, *, case, run, artifact_dir: Path) -> Evaluation:
    if run.solution is None:
        return Evaluation(hard_feasible=None)
    return spec.evaluate(case=case, run=run, artifact_dir=artifact_dir)


def _row(
    *,
    spec: BenchmarkSpec,
    case,
    run,
    evaluation: Evaluation,
    wall_time_tolerance: float,
) -> BenchmarkRow:
    overshoot_seconds = max(0.0, run.actual_time_seconds - run.time_limit_seconds)
    overshoot_ratio = (
        overshoot_seconds / run.time_limit_seconds if run.time_limit_seconds else 0.0
    )
    native_fields = {}
    native_fields.update(case.native_fields)
    native_fields.update(evaluation.native_fields)
    return BenchmarkRow(
        benchmark_name=spec.name,
        benchmark_category=spec.category,
        dataset=case.dataset,
        dataset_set=case.dataset_set,
        instance=case.instance,
        instance_size=case.instance_size,
        solver=run.solver,
        time_limit_seconds=run.time_limit_seconds,
        actual_time_seconds=run.actual_time_seconds,
        overshoot_seconds=overshoot_seconds,
        overshoot_ratio=overshoot_ratio,
        wall_time_over_limit=(
            run.actual_time_seconds > run.time_limit_seconds * wall_time_tolerance
        ),
        watchdog_limit_seconds=run.watchdog_limit_seconds,
        watchdog_killed=run.watchdog_killed,
        run_error=run.run_error,
        hard_feasible=evaluation.hard_feasible,
        cost=evaluation.cost,
        reported_cost=evaluation.reported_cost,
        fresh_cost=evaluation.fresh_cost,
        reference_cost=evaluation.reference_cost,
        quality_ratio=evaluation.quality_ratio,
        validation_error=evaluation.validation_error,
        solution_artifact=evaluation.solution_artifact,
        native_fields=native_fields,
    )
