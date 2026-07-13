"""PostgreSQL persistence for benchmark runs."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from solverforge_bench.etl import benchmark_rows_to_postgres_frame
from solverforge_bench.model import BenchmarkRow, SolverVersion
from solverforge_bench.redaction import redact_sensitive_command_args
from solverforge_bench.validation import (
    validate_solver_versions,
    validate_unique_solvers,
)


DEFAULT_DATABASE_URL = "postgresql://postgres@localhost/solverforge_bench"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PostgresConfig:
    database_url: str
    run_kind: str
    nightly: bool
    release_tag: str | None
    run_stamp: str
    benchmark_name: str
    benchmark_category: str
    output_path: Path
    artifact_dir: Path
    log_path: Path | None
    solvers: list[str]
    solver_versions: dict[str, SolverVersion]
    time_limits_seconds: list[int]
    command_args: list[str]
    repo_root: Path
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        validate_unique_solvers(self.solvers)
        validate_solver_versions(self.solvers, self.solver_versions)


class PostgresResultWriter:
    def __init__(self, config: PostgresConfig):
        self.config = config
        self.run_id = uuid.uuid4()
        self._conn = None
        self._row_index = 0
        self._solver_version_ids: dict[str, int] = {}

    def __enter__(self) -> "PostgresResultWriter":
        psycopg, Jsonb = _load_psycopg()
        self._jsonb = Jsonb
        self._conn = psycopg.connect(self.config.database_url, autocommit=True)
        run_inserted = False
        try:
            self._insert_run()
            run_inserted = True
            self._insert_solver_versions()
        except BaseException as exc:
            if run_inserted:
                self._finish_run_after_open_failure(exc)
            self._conn.close()
            self._conn = None
            raise
        return self

    def __exit__(self, exc_type, exc, _tb) -> None:
        if self._conn is not None:
            self._finish_run(exc_type=exc_type, exc=exc)
            self._conn.close()

    def write_row(self, row: BenchmarkRow) -> None:
        if self._conn is None:
            raise RuntimeError("PostgresResultWriter is not open")

        frame = benchmark_rows_to_postgres_frame(
            [row], run_id=self.run_id, row_offset=self._row_index
        )
        next_row_index = self._row_index + 1
        with self._conn.transaction():
            self._insert_result_frame(frame)
            self._update_result_count(next_row_index)
        self._row_index = next_row_index

    def _insert_result_frame(self, frame) -> None:
        with self._conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO benchmark_results (
                    run_id,
                    row_index,
                    benchmark_name,
                    benchmark_category,
                    dataset,
                    dataset_set,
                    instance,
                    instance_size,
                    solver,
                    solver_version_id,
                    time_limit_seconds,
                    actual_time_seconds,
                    overshoot_seconds,
                    overshoot_ratio,
                    wall_time_over_limit,
                    watchdog_limit_seconds,
                    watchdog_killed,
                    fair_start_valid,
                    fair_start_error,
                    fair_start_witness,
                    run_error,
                    solver_stdout_path,
                    solver_stderr_path,
                    hard_feasible,
                    cost,
                    reported_cost,
                    fresh_cost,
                    reference_cost,
                    quality_ratio,
                    validation_error,
                    solution_artifact,
                    native_fields,
                    row_payload
                )
                VALUES (
                    %(run_id)s,
                    %(row_index)s,
                    %(benchmark_name)s,
                    %(benchmark_category)s,
                    %(dataset)s,
                    %(dataset_set)s,
                    %(instance)s,
                    %(instance_size)s,
                    %(solver)s,
                    %(solver_version_id)s,
                    %(time_limit_seconds)s,
                    %(actual_time_seconds)s,
                    %(overshoot_seconds)s,
                    %(overshoot_ratio)s,
                    %(wall_time_over_limit)s,
                    %(watchdog_limit_seconds)s,
                    %(watchdog_killed)s,
                    %(fair_start_valid)s,
                    %(fair_start_error)s,
                    %(fair_start_witness)s,
                    %(run_error)s,
                    %(solver_stdout_path)s,
                    %(solver_stderr_path)s,
                    %(hard_feasible)s,
                    %(cost)s,
                    %(reported_cost)s,
                    %(fresh_cost)s,
                    %(reference_cost)s,
                    %(quality_ratio)s,
                    %(validation_error)s,
                    %(solution_artifact)s,
                    %(native_fields)s,
                    %(row_payload)s
                )
                """,
                [self._postgres_params(row) for row in frame.iter_rows(named=True)],
            )

    def _update_result_count(self, result_count: int) -> None:
        if self._conn is None:
            raise RuntimeError("PostgresResultWriter is not open")

        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_runs
                SET result_count = %(result_count)s
                WHERE id = %(id)s
                """,
                {
                    "id": self.run_id,
                    "result_count": result_count,
                },
            )

    def _postgres_params(self, row: dict[str, Any]) -> dict[str, Any]:
        params = dict(row)
        params["solver_version_id"] = self._solver_version_ids[params["solver"]]
        params["fair_start_witness"] = self._jsonb(
            _json_safe(params["fair_start_witness"])
        )
        params["native_fields"] = self._jsonb(_json_safe(params["native_fields"]))
        params["row_payload"] = self._jsonb(_json_safe(params["row_payload"]))
        return params

    def _insert_solver_versions(self) -> None:
        if self._conn is None:
            raise RuntimeError("PostgresResultWriter is not open")

        with self._conn.cursor() as cur:
            for solver in self.config.solvers:
                version = self.config.solver_versions[solver]
                cur.execute(
                    """
                    INSERT INTO benchmark_solver_versions (
                        run_id,
                        solver,
                        solver_version,
                        version_source,
                        metadata
                    )
                    VALUES (
                        %(run_id)s,
                        %(solver)s,
                        %(solver_version)s,
                        %(version_source)s,
                        %(metadata)s
                    )
                    RETURNING id
                    """,
                    {
                        "run_id": self.run_id,
                        "solver": version.solver,
                        "solver_version": version.version,
                        "version_source": version.source,
                        "metadata": self._jsonb(_json_safe(version.metadata)),
                    },
                )
                inserted_id = cur.fetchone()[0]
                self._solver_version_ids[solver] = inserted_id

    def _insert_run(self) -> None:
        if self._conn is None:
            raise RuntimeError("PostgresResultWriter is not open")

        git_commit, git_dirty = _git_state(self.config.repo_root)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO benchmark_runs (
                    id,
                    run_kind,
                    nightly,
                    release_tag,
                    run_stamp,
                    benchmark_name,
                    benchmark_category,
                    output_path,
                    artifact_dir,
                    log_path,
                    solvers,
                    time_limits_seconds,
                    command_args,
                    repo_root,
                    git_commit,
                    git_dirty,
                    python_version,
                    metadata
                )
                VALUES (
                    %(id)s,
                    %(run_kind)s,
                    %(nightly)s,
                    %(release_tag)s,
                    %(run_stamp)s,
                    %(benchmark_name)s,
                    %(benchmark_category)s,
                    %(output_path)s,
                    %(artifact_dir)s,
                    %(log_path)s,
                    %(solvers)s,
                    %(time_limits_seconds)s,
                    %(command_args)s,
                    %(repo_root)s,
                    %(git_commit)s,
                    %(git_dirty)s,
                    %(python_version)s,
                    %(metadata)s
                )
                """,
                {
                    "id": self.run_id,
                    "run_kind": self.config.run_kind,
                    "nightly": self.config.nightly,
                    "release_tag": self.config.release_tag,
                    "run_stamp": self.config.run_stamp,
                    "benchmark_name": self.config.benchmark_name,
                    "benchmark_category": self.config.benchmark_category,
                    "output_path": str(self.config.output_path),
                    "artifact_dir": str(self.config.artifact_dir),
                    "log_path": (
                        str(self.config.log_path) if self.config.log_path else None
                    ),
                    "solvers": self.config.solvers,
                    "time_limits_seconds": self.config.time_limits_seconds,
                    "command_args": self._jsonb(self.config.command_args),
                    "repo_root": str(self.config.repo_root),
                    "git_commit": git_commit,
                    "git_dirty": git_dirty,
                    "python_version": sys.version,
                    "metadata": self._jsonb(_json_safe(self.config.metadata)),
                },
            )

    def _finish_run(self, *, exc_type, exc) -> None:
        if self._conn is None:
            raise RuntimeError("PostgresResultWriter is not open")

        if exc_type is None:
            status = "completed"
            failure_error = None
        else:
            status = "failed"
            failure_error = f"{exc_type.__name__}: {exc}"

        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_runs
                SET
                    status = %(status)s,
                    completed_at = now(),
                    failure_error = %(failure_error)s,
                    result_count = %(result_count)s
                WHERE id = %(id)s
                """,
                {
                    "id": self.run_id,
                    "status": status,
                    "failure_error": failure_error,
                    "result_count": self._row_index,
                },
            )

    def _finish_run_after_open_failure(self, exc: BaseException) -> None:
        try:
            self._finish_run(exc_type=type(exc), exc=exc)
        except Exception:
            LOGGER.warning(
                "postgres_run_finish_failed_after_setup_error run_id=%s",
                self.run_id,
                exc_info=True,
            )


def database_url_from_args(args: Any) -> str:
    return (
        str(args.postgres_url)
        if getattr(args, "postgres_url", None)
        else os.environ.get("BENCH_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )


def make_postgres_config(
    *,
    args: Any,
    spec: Any,
    output_path: Path,
    artifact_dir: Path,
    solvers: Iterable[str],
    solver_versions: dict[str, SolverVersion],
    time_limits: Iterable[int],
) -> PostgresConfig:
    return PostgresConfig(
        database_url=database_url_from_args(args),
        run_kind=args.run_kind,
        nightly=args.nightly,
        release_tag=args.release_tag,
        run_stamp=args.run_stamp,
        benchmark_name=spec.name,
        benchmark_category=spec.category,
        output_path=output_path,
        artifact_dir=artifact_dir,
        log_path=getattr(args, "log_path", None),
        solvers=list(solvers),
        solver_versions=solver_versions,
        time_limits_seconds=list(time_limits),
        command_args=redact_sensitive_command_args(getattr(args, "argv", [])),
        repo_root=Path(args.repo_root),
        metadata={
            "dataset_set": getattr(args, "dataset_set", None),
            "datasets": getattr(args, "datasets", None),
            "num_instances": getattr(args, "num_instances", None),
            "nightly": getattr(args, "nightly", None),
            "wall_time_tolerance": getattr(args, "wall_time_tolerance", None),
            "watchdog_multiplier": getattr(args, "watchdog_multiplier", None),
            "watchdog_grace_seconds": getattr(args, "watchdog_grace_seconds", None),
            "log_level": getattr(args, "log_level", None),
            "show_solver_output": getattr(args, "show_solver_output", None),
            "capture_solver_output": getattr(args, "capture_solver_output", None),
            "fair_start_witness_version": 1,
            "fair_start_contract": (
                "Solvers must start from unassigned scalar variables or empty "
                "list variables, with no adapter-owned hints, preliminary "
                "solves, fallback schedules, or reference-solution reads."
            ),
            "config_path": (
                str(args.config) if getattr(args, "config", None) else None
            ),
        },
    )


def _load_psycopg():
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PostgreSQL saving requires psycopg. Install project dependencies "
            "with `pip install -e .`."
        ) from exc
    return psycopg, Jsonb


def _git_state(repo_root: Path) -> tuple[str | None, bool]:
    commit = _git_output(repo_root, "rev-parse", "HEAD")
    dirty = bool(_git_output(repo_root, "status", "--porcelain"))
    return commit, dirty


def _git_output(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
