#!/usr/bin/env python3
"""Normalize benchmark CSV output into a database-ready row schema."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA_COLUMNS = [
    "run_id",
    "benchmark_category",
    "benchmark_name",
    "dataset",
    "dataset_set",
    "instance",
    "instance_size",
    "nurses",
    "weeks",
    "solver",
    "time_limit_seconds",
    "actual_time_seconds",
    "hard_feasible",
    "cost",
    "reference_cost",
    "quality_ratio",
    "validation_error",
    "source_file",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize SolverForge benchmark CSV files for database loading."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Native benchmark CSV file."
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
        "--category",
        choices=["auto", "cvrp", "employee_scheduling"],
        default="auto",
        help="Benchmark category. Defaults to inference from CSV headers.",
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
    rows = read_csv(args.input)
    category = infer_category(rows, args.category)
    normalized = [
        normalize_row(row, category=category, run_id=run_id, source_file=args.input)
        for row in rows
    ]
    write_rows(args.output, normalized, args.format)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def infer_category(rows: list[dict[str, str]], requested: str) -> str:
    if requested != "auto":
        return requested
    if not rows:
        raise ValueError("Cannot infer benchmark category from an empty CSV.")
    headers = set(rows[0])
    if {
        "Dataset Set",
        "Nurses",
        "Weeks",
        "Hard Feasible",
        "Validation Error",
    } <= headers:
        return "employee_scheduling"
    if {"Instance", "Size", "Solution Quality"} <= headers:
        return "cvrp"
    raise ValueError(f"Cannot infer benchmark category from headers: {sorted(headers)}")


def normalize_row(
    row: dict[str, str],
    *,
    category: str,
    run_id: str,
    source_file: Path,
) -> dict[str, object | None]:
    if category == "cvrp":
        quality_ratio = as_float(row.get("Solution Quality"))
        return {
            "run_id": run_id,
            "benchmark_category": "list_variable",
            "benchmark_name": "cvrp",
            "dataset": "CVRPLIB-X",
            "dataset_set": "canonical",
            "instance": blank_to_none(row.get("Instance")),
            "instance_size": as_int(row.get("Size")),
            "nurses": None,
            "weeks": None,
            "solver": blank_to_none(row.get("Solver")),
            "time_limit_seconds": as_int(row.get("Time Limit (s)")),
            "actual_time_seconds": as_float(row.get("Actual Time (s)")),
            "hard_feasible": quality_ratio is not None and quality_ratio >= 0,
            "cost": None,
            "reference_cost": None,
            "quality_ratio": None if quality_ratio == -1 else quality_ratio,
            "validation_error": "validation_failed" if quality_ratio == -1 else "",
            "source_file": str(source_file),
        }
    if category == "employee_scheduling":
        return {
            "run_id": run_id,
            "benchmark_category": "scalar_variable",
            "benchmark_name": "employee_scheduling",
            "dataset": "INRC-II",
            "dataset_set": blank_to_none(row.get("Dataset Set")),
            "instance": blank_to_none(row.get("Instance")),
            "instance_size": as_int(row.get("Nurses")),
            "nurses": as_int(row.get("Nurses")),
            "weeks": as_int(row.get("Weeks")),
            "solver": blank_to_none(row.get("Solver")),
            "time_limit_seconds": as_int(row.get("Time Limit (s)")),
            "actual_time_seconds": as_float(row.get("Actual Time (s)")),
            "hard_feasible": as_bool(row.get("Hard Feasible")),
            "cost": as_int(row.get("Cost")),
            "reference_cost": as_int(row.get("Reference Cost")),
            "quality_ratio": as_float(row.get("Quality Ratio")),
            "validation_error": blank_to_none(row.get("Validation Error")) or "",
            "source_file": str(source_file),
        }
    raise ValueError(f"Unsupported category: {category}")


def write_rows(
    path: Path, rows: Iterable[dict[str, object | None]], output_format: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = list(rows)
    if output_format == "csv":
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=SCHEMA_COLUMNS, extrasaction="raise"
            )
            writer.writeheader()
            writer.writerows(serialize_csv_row(row) for row in materialized)
        return
    with path.open("w") as handle:
        for row in materialized:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


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


def serialize_csv_row(row: dict[str, object | None]) -> dict[str, object | None]:
    serialized = {}
    for key, value in row.items():
        if isinstance(value, bool):
            serialized[key] = "true" if value else "false"
        else:
            serialized[key] = value
    return serialized


if __name__ == "__main__":
    main()
