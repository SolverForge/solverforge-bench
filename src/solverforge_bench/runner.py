"""Shared benchmark run matrix and row construction."""

from __future__ import annotations

import fcntl
import logging
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from solverforge_bench.csv import IncrementalCsvWriter, benchmark_columns
from solverforge_bench.execution import run_solver, watchdog_limit_seconds
from solverforge_bench.logging import (
    configure_run_logging,
    run_log_path,
    solver_capture_dir,
    solver_output_paths,
)
from solverforge_bench.model import BenchmarkRow, BenchmarkSpec, Evaluation
from solverforge_bench.postgres import PostgresResultWriter, make_postgres_config
from solverforge_bench.validation import (
    validate_solver_versions,
    validate_unique_solvers,
)

LOGGER = logging.getLogger(__name__)


def run_benchmark(spec: BenchmarkSpec, args: Any) -> Path:
    run_stamp = getattr(args, "run_stamp")
    output_path = (
        Path(args.output) if args.output else spec.output_path(args, run_stamp)
    )
    artifact_dir = spec.artifact_dir(args, run_stamp)
    log_path = run_log_path(
        args=args,
        benchmark_name=spec.name,
    )
    configure_run_logging(level=args.log_level, log_file=log_path)
    args.log_path = log_path
    solvers = validate_unique_solvers(args.solver or spec.default_solvers)
    time_limits = args.time_limits or spec.default_time_limits
    solver_versions = spec.solver_versions(solvers)
    validate_solver_versions(solvers, solver_versions)
    solver_log_dir = solver_capture_dir(
        log_path=log_path,
        benchmark_name=spec.name,
        run_stamp=run_stamp,
        explicit_log_file=bool(getattr(args, "log_file", None)),
    )

    LOGGER.info(
        "benchmark_start benchmark=%s category=%s solvers=%s time_limits=%s "
        "output=%s artifact_dir=%s log_path=%s run_kind=%s nightly=%s "
        "solver_versions=%s",
        spec.name,
        spec.category,
        ",".join(solvers),
        ",".join(str(item) for item in time_limits),
        output_path,
        artifact_dir,
        log_path,
        args.run_kind,
        args.nightly,
        {name: version.version for name, version in solver_versions.items()},
    )

    lock_path = _benchmark_lock_path()
    lock_handle = _acquire_benchmark_lock(lock_path) if lock_path else None
    try:
        postgres_writer = None
        with ExitStack() as stack:
            writer = stack.enter_context(
                IncrementalCsvWriter(
                    output_path, columns=benchmark_columns(spec.native_columns)
                )
            )
            LOGGER.info("csv_writer_opened path=%s", output_path)
            if args.save_postgres:
                postgres_writer = stack.enter_context(
                    PostgresResultWriter(
                        make_postgres_config(
                            args=args,
                            spec=spec,
                            output_path=output_path,
                            artifact_dir=artifact_dir,
                            solvers=solvers,
                            solver_versions=solver_versions,
                            time_limits=time_limits,
                        )
                    )
                )
                args.postgres_run_id = str(postgres_writer.run_id)
                LOGGER.info("postgres_run_opened run_id=%s", args.postgres_run_id)

            for case in spec.cases(args):
                LOGGER.info(
                    "case_start dataset=%s dataset_set=%s instance=%s "
                    "instance_size=%s",
                    case.dataset,
                    case.dataset_set,
                    case.instance,
                    case.instance_size,
                )
                for time_limit in time_limits:
                    watchdog_seconds = watchdog_limit_seconds(
                        time_limit,
                        multiplier=args.watchdog_multiplier,
                        grace_seconds=args.watchdog_grace_seconds,
                    )
                    for solver_name in solvers:
                        stdout_path, stderr_path = solver_output_paths(
                            log_dir=solver_log_dir,
                            instance_name=case.instance,
                            solver_name=solver_name,
                            time_limit_seconds=time_limit,
                        )
                        captured_stdout_path = (
                            stdout_path if args.capture_solver_output else None
                        )
                        captured_stderr_path = (
                            stderr_path if args.capture_solver_output else None
                        )
                        LOGGER.info(
                            "solver_start instance=%s solver=%s time_limit=%s "
                            "watchdog=%s stdout=%s stderr=%s",
                            case.instance,
                            solver_name,
                            time_limit,
                            watchdog_seconds,
                            captured_stdout_path,
                            captured_stderr_path,
                        )
                        run = run_solver(
                            solver_name=solver_name,
                            solver_factory=spec.create_solver,
                            solution_model=spec.solution_model,
                            instance=case.payload,
                            time_limit_seconds=time_limit,
                            watchdog_seconds=watchdog_seconds,
                            stdout_path=captured_stdout_path,
                            stderr_path=captured_stderr_path,
                            capture_solver_output=args.capture_solver_output,
                            show_solver_output=args.show_solver_output,
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
                            solver_version=solver_versions[run.solver].version,
                            wall_time_tolerance=args.wall_time_tolerance,
                        )
                        writer.write_row(row.as_dict())
                        if postgres_writer is not None:
                            postgres_writer.write_row(row)
                        LOGGER.info(
                            "solver_end instance=%s solver=%s time_limit=%s "
                            "actual_time=%.6f watchdog_killed=%s run_error=%s "
                            "hard_feasible=%s",
                            case.instance,
                            solver_name,
                            time_limit,
                            run.actual_time_seconds,
                            run.watchdog_killed,
                            run.run_error,
                            evaluation.hard_feasible,
                        )
    finally:
        if lock_handle is not None:
            _release_benchmark_lock(lock_handle)

    LOGGER.info("benchmark_completed benchmark=%s output=%s", spec.name, output_path)
    return output_path


def _benchmark_lock_path() -> Path | None:
    explicit = os.environ.get("BENCH_LOCK") or os.environ.get("SOLVERFORGE_BENCH_LOCK")
    if explicit:
        return Path(explicit)
    return None


def _acquire_benchmark_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    LOGGER.info("benchmark_lock_wait path=%s", lock_path)
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()}\n")
    handle.flush()
    LOGGER.info("benchmark_lock_acquired path=%s", lock_path)
    return handle


def _release_benchmark_lock(handle) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        LOGGER.info("benchmark_lock_released path=%s", handle.name)
    finally:
        handle.close()


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
    solver_version: str,
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
        solver_version=solver_version,
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
        solver_stdout_path=run.solver_stdout_path,
        solver_stderr_path=run.solver_stderr_path,
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
