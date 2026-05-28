"""Polars-based benchmark result ETL helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import polars as pl

from solverforge_bench.model import BenchmarkRow


POSTGRES_RESULT_COLUMNS = [
    "run_id",
    "row_index",
    "benchmark_name",
    "benchmark_category",
    "dataset",
    "dataset_set",
    "instance",
    "instance_size",
    "solver",
    "time_limit_seconds",
    "actual_time_seconds",
    "overshoot_seconds",
    "overshoot_ratio",
    "wall_time_over_limit",
    "watchdog_limit_seconds",
    "watchdog_killed",
    "fair_start_valid",
    "fair_start_error",
    "fair_start_witness",
    "run_error",
    "solver_stdout_path",
    "solver_stderr_path",
    "hard_feasible",
    "cost",
    "reported_cost",
    "fresh_cost",
    "reference_cost",
    "quality_ratio",
    "validation_error",
    "solution_artifact",
    "native_fields",
    "row_payload",
]


def benchmark_rows_to_postgres_frame(
    rows: Iterable[BenchmarkRow], *, run_id: Any, row_offset: int = 0
) -> pl.DataFrame:
    """Transform benchmark rows into the typed PostgreSQL result frame."""

    records = [
        _postgres_record(row, run_id=run_id, row_index=index)
        for index, row in enumerate(rows, start=row_offset + 1)
    ]
    return frame_from_records(records, columns=POSTGRES_RESULT_COLUMNS)


def frame_from_records(
    records: Iterable[dict[str, Any]], *, columns: list[str]
) -> pl.DataFrame:
    materialized = list(records)
    if not materialized:
        return pl.DataFrame({column: [] for column in columns})
    return pl.DataFrame(materialized, strict=False).select(columns)


def read_csv_frame(path: Path) -> pl.DataFrame:
    """Read a benchmark CSV artifact as strings for deterministic normalization."""

    return pl.read_csv(path, infer_schema_length=0, null_values=[""])


def write_csv_frame(path: Path, frame: pl.DataFrame, *, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.select(columns).write_csv(path)


def _postgres_record(
    row: BenchmarkRow, *, run_id: Any, row_index: int
) -> dict[str, Any]:
    row_payload = row.as_dict()
    return {
        "run_id": run_id,
        "row_index": row_index,
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
        "fair_start_valid": row.fair_start_valid,
        "fair_start_error": row.fair_start_error,
        "fair_start_witness": row.fair_start_witness,
        "run_error": row.run_error,
        "solver_stdout_path": row.solver_stdout_path,
        "solver_stderr_path": row.solver_stderr_path,
        "hard_feasible": row.hard_feasible,
        "cost": _float_or_none(row.cost),
        "reported_cost": _float_or_none(row.reported_cost),
        "fresh_cost": _float_or_none(row.fresh_cost),
        "reference_cost": _float_or_none(row.reference_cost),
        "quality_ratio": _float_or_none(row.quality_ratio),
        "validation_error": row.validation_error,
        "solution_artifact": row.solution_artifact,
        "native_fields": row.native_fields,
        "row_payload": row_payload,
    }


def _float_or_none(value: float | int | None) -> float | None:
    return float(value) if value is not None else None
