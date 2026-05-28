"""Stable global CSV writing for all benchmark specs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable


GLOBAL_COLUMNS = [
    "benchmark_name",
    "benchmark_category",
    "dataset",
    "dataset_set",
    "instance",
    "instance_size",
    "solver",
    "solver_version",
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
    "nurses",
    "weeks",
    "validator_model_delta",
    "score_drift",
    "num_jobs",
    "num_machines",
    "num_operations",
    "source_family",
    "known_best_makespan",
    "lower_bound_makespan",
    "upper_bound_makespan",
    "makespan_gap_to_best",
]

NORMALIZED_COLUMNS = ["run_id", *GLOBAL_COLUMNS, "source_file"]


def benchmark_columns(native_columns: Iterable[str]) -> list[str]:
    columns = [*GLOBAL_COLUMNS, *native_columns]
    return list(dict.fromkeys(columns))


class IncrementalCsvWriter:
    def __init__(self, path: Path, *, columns: Iterable[str] = GLOBAL_COLUMNS):
        self.path = path
        self.columns = list(columns)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(
            self._handle,
            fieldnames=self.columns,
            extrasaction="ignore",
        )
        self._writer.writeheader()
        self._handle.flush()

    def write_row(self, row: dict[str, Any]) -> None:
        self._writer.writerow(
            {column: _csv_value(row.get(column)) for column in self.columns}
        )
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "IncrementalCsvWriter":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value
