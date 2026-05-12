"""PostgreSQL persistence for benchmark runs."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from solverforge_bench.model import BenchmarkRow


DEFAULT_DATABASE_URL = "postgresql://postgres@localhost/solverforge_bench"


@dataclass(frozen=True)
class PostgresConfig:
    database_url: str
    run_kind: str
    release_tag: str | None
    run_stamp: str
    benchmark_name: str
    benchmark_category: str
    output_path: Path
    artifact_dir: Path
    solvers: list[str]
    time_limits_seconds: list[int]
    command_args: list[str]
    repo_root: Path
    metadata: dict[str, Any]


class PostgresResultWriter:
    def __init__(self, config: PostgresConfig):
        self.config = config
        self.run_id = uuid.uuid4()
        self._conn = None
        self._row_index = 0

    def __enter__(self) -> "PostgresResultWriter":
        psycopg, Jsonb = _load_psycopg()
        self._jsonb = Jsonb
        self._conn = psycopg.connect(self.config.database_url, autocommit=True)
        self._insert_run()
        return self

    def __exit__(self, exc_type, exc, _tb) -> None:
        if self._conn is not None:
            self._finish_run(exc_type=exc_type, exc=exc)
            self._conn.close()

    def write_row(self, row: BenchmarkRow) -> None:
        if self._conn is None:
            raise RuntimeError("PostgresResultWriter is not open")

        self._row_index += 1
        row_payload = row.as_dict()
        native_fields = _json_safe(row.native_fields)
        with self._conn.cursor() as cur:
            cur.execute(
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
                    time_limit_seconds,
                    actual_time_seconds,
                    overshoot_seconds,
                    overshoot_ratio,
                    wall_time_over_limit,
                    watchdog_limit_seconds,
                    watchdog_killed,
                    run_error,
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
                    %(time_limit_seconds)s,
                    %(actual_time_seconds)s,
                    %(overshoot_seconds)s,
                    %(overshoot_ratio)s,
                    %(wall_time_over_limit)s,
                    %(watchdog_limit_seconds)s,
                    %(watchdog_killed)s,
                    %(run_error)s,
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
                {
                    "run_id": self.run_id,
                    "row_index": self._row_index,
                    "benchmark_name": row.benchmark_name,
                    "benchmark_category": row.benchmark_category,
                    "dataset": row.dataset,
                    "dataset_set": row.dataset_set,
                    "instance": row.instance,
                    "instance_size": row.instance_size,
                    "solver": row.solver,
                    "time_limit_seconds": row.time_limit_seconds,
                    "actual_time_seconds": row.actual_time_seconds,
                    "overshoot_seconds": row.overshoot_seconds,
                    "overshoot_ratio": row.overshoot_ratio,
                    "wall_time_over_limit": row.wall_time_over_limit,
                    "watchdog_limit_seconds": row.watchdog_limit_seconds,
                    "watchdog_killed": row.watchdog_killed,
                    "run_error": row.run_error,
                    "hard_feasible": row.hard_feasible,
                    "cost": _float_or_none(row.cost),
                    "reported_cost": _float_or_none(row.reported_cost),
                    "fresh_cost": _float_or_none(row.fresh_cost),
                    "reference_cost": _float_or_none(row.reference_cost),
                    "quality_ratio": _float_or_none(row.quality_ratio),
                    "validation_error": row.validation_error,
                    "solution_artifact": row.solution_artifact,
                    "native_fields": self._jsonb(native_fields),
                    "row_payload": self._jsonb(_json_safe(row_payload)),
                },
            )

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
                    release_tag,
                    run_stamp,
                    benchmark_name,
                    benchmark_category,
                    output_path,
                    artifact_dir,
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
                    %(release_tag)s,
                    %(run_stamp)s,
                    %(benchmark_name)s,
                    %(benchmark_category)s,
                    %(output_path)s,
                    %(artifact_dir)s,
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
                    "release_tag": self.config.release_tag,
                    "run_stamp": self.config.run_stamp,
                    "benchmark_name": self.config.benchmark_name,
                    "benchmark_category": self.config.benchmark_category,
                    "output_path": str(self.config.output_path),
                    "artifact_dir": str(self.config.artifact_dir),
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
    time_limits: Iterable[int],
) -> PostgresConfig:
    return PostgresConfig(
        database_url=database_url_from_args(args),
        run_kind=args.run_kind,
        release_tag=args.release_tag,
        run_stamp=args.run_stamp,
        benchmark_name=spec.name,
        benchmark_category=spec.category,
        output_path=output_path,
        artifact_dir=artifact_dir,
        solvers=list(solvers),
        time_limits_seconds=list(time_limits),
        command_args=list(getattr(args, "argv", [])),
        repo_root=Path(args.repo_root),
        metadata={
            "dataset_set": getattr(args, "dataset_set", None),
            "datasets": getattr(args, "datasets", None),
            "num_instances": getattr(args, "num_instances", None),
            "wall_time_tolerance": getattr(args, "wall_time_tolerance", None),
            "watchdog_multiplier": getattr(args, "watchdog_multiplier", None),
            "watchdog_grace_seconds": getattr(args, "watchdog_grace_seconds", None),
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


def _float_or_none(value: float | int | None) -> float | None:
    return float(value) if value is not None else None


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
