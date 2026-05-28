#!/usr/bin/env python3.14
"""Normalize benchmark CSV output into a database-ready row schema."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from _venv_bootstrap import ensure_repo_venv

REPO_ROOT = Path(__file__).resolve().parents[1]
ensure_repo_venv(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT / "src"))

from solverforge_bench.csv import GLOBAL_COLUMNS, NORMALIZED_COLUMNS  # noqa: E402
from solverforge_bench.etl import (  # noqa: E402
    frame_from_records,
    read_csv_frame,
    write_csv_frame,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize SolverForge benchmark CSV files for database loading."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Global benchmark CSV file."
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Normalized output path. Parent directories are created.",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "ndjson"],
        default="csv",
        help="Normalized output format.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Stable run identifier to attach to every row. Defaults to UTC timestamp.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    source = read_csv_frame(args.input)
    validate_global_schema(source.columns)
    normalized = frame_from_records(
        [
            normalize_global_row(row, run_id=run_id, source_file=args.input)
            for row in source.iter_rows(named=True)
        ],
        columns=NORMALIZED_COLUMNS,
    )
    write_rows(args.output, normalized, args.format)


def validate_global_schema(columns: list[str]) -> None:
    missing = [column for column in GLOBAL_COLUMNS if column not in columns]
    if missing:
        raise ValueError(
            "Input is not a SolverForge global benchmark CSV; missing column(s): "
            + ", ".join(missing)
        )


def normalize_global_row(
    row: dict[str, str],
    *,
    run_id: str,
    source_file: Path,
) -> dict[str, object | None]:
    return {
        "run_id": run_id,
        "benchmark_name": blank_to_none(row.get("benchmark_name")),
        "benchmark_category": blank_to_none(row.get("benchmark_category")),
        "dataset": blank_to_none(row.get("dataset")),
        "dataset_set": blank_to_none(row.get("dataset_set")),
        "instance": blank_to_none(row.get("instance")),
        "instance_size": as_int(row.get("instance_size")),
        "solver": blank_to_none(row.get("solver")),
        "solver_version": blank_to_none(row.get("solver_version")),
        "time_limit_seconds": as_int(row.get("time_limit_seconds")),
        "actual_time_seconds": as_float(row.get("actual_time_seconds")),
        "overshoot_seconds": as_float(row.get("overshoot_seconds")),
        "overshoot_ratio": as_float(row.get("overshoot_ratio")),
        "wall_time_over_limit": as_bool(row.get("wall_time_over_limit")),
        "watchdog_limit_seconds": as_float(row.get("watchdog_limit_seconds")),
        "watchdog_killed": as_bool(row.get("watchdog_killed")),
        "fair_start_valid": as_bool(row.get("fair_start_valid")),
        "fair_start_error": blank_to_none(row.get("fair_start_error")),
        "fair_start_witness": as_json_text(row.get("fair_start_witness")),
        "run_error": blank_to_none(row.get("run_error")),
        "solver_stdout_path": blank_to_none(row.get("solver_stdout_path")),
        "solver_stderr_path": blank_to_none(row.get("solver_stderr_path")),
        "hard_feasible": as_bool(row.get("hard_feasible")),
        "cost": as_float(row.get("cost")),
        "reported_cost": as_float(row.get("reported_cost")),
        "fresh_cost": as_float(row.get("fresh_cost")),
        "reference_cost": as_float(row.get("reference_cost")),
        "quality_ratio": as_float(row.get("quality_ratio")),
        "validation_error": blank_to_none(row.get("validation_error")) or "",
        "solution_artifact": blank_to_none(row.get("solution_artifact")),
        "nurses": as_int(row.get("nurses")),
        "weeks": as_int(row.get("weeks")),
        "validator_model_delta": as_float(row.get("validator_model_delta")),
        "score_drift": as_bool(row.get("score_drift")),
        "num_jobs": as_int(row.get("num_jobs")),
        "num_machines": as_int(row.get("num_machines")),
        "num_operations": as_int(row.get("num_operations")),
        "source_family": blank_to_none(row.get("source_family")),
        "known_best_makespan": as_int(row.get("known_best_makespan")),
        "lower_bound_makespan": as_int(row.get("lower_bound_makespan")),
        "upper_bound_makespan": as_int(row.get("upper_bound_makespan")),
        "makespan_gap_to_best": as_float(row.get("makespan_gap_to_best")),
        "source_file": str(source_file),
    }


def write_rows(path: Path, rows, output_format: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        write_csv_frame(path, rows, columns=NORMALIZED_COLUMNS)
        return
    rows.select(NORMALIZED_COLUMNS).write_ndjson(path)


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    return value


def as_int(value: str | None) -> int | None:
    value = blank_to_none(value)
    if value is None:
        return None
    return int(float(value))


def as_float(value: str | None) -> float | None:
    value = blank_to_none(value)
    if value is None:
        return None
    return float(value)


def as_bool(value: str | None) -> bool | None:
    value = blank_to_none(value)
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes"}


def as_json_text(value: str | None) -> str | None:
    value = blank_to_none(value)
    if value is None:
        return None
    json.loads(value)
    return value


if __name__ == "__main__":
    main()
