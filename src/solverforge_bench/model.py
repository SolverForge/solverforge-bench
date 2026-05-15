"""Shared benchmark contracts and row model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol


SolverFactory = Callable[..., Callable[[Any, int], Any]]


class NoSolutionFoundError(RuntimeError):
    """Raised when a solver finishes without a usable solution."""


@dataclass(frozen=True)
class SolverVersion:
    solver: str
    version: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkCase:
    dataset: str
    dataset_set: str
    instance: str
    instance_size: int | None
    payload: Any
    reference_solution: Any | None = None
    context: dict[str, Any] = field(default_factory=dict)
    native_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SolverRun:
    solver: str
    time_limit_seconds: int
    actual_time_seconds: float
    watchdog_limit_seconds: float
    watchdog_killed: bool
    solution: Any | None
    run_error: str | None
    exit_code: int | None
    solver_stdout_path: str | None = None
    solver_stderr_path: str | None = None


@dataclass(frozen=True)
class Evaluation:
    hard_feasible: bool | None = None
    cost: float | int | None = None
    reported_cost: float | int | None = None
    fresh_cost: float | int | None = None
    reference_cost: float | int | None = None
    quality_ratio: float | None = None
    validation_error: str | None = None
    solution_artifact: str | None = None
    native_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkRow:
    benchmark_name: str
    benchmark_category: str
    dataset: str
    dataset_set: str
    instance: str
    instance_size: int | None
    solver: str
    solver_version: str
    time_limit_seconds: int
    actual_time_seconds: float
    overshoot_seconds: float
    overshoot_ratio: float
    wall_time_over_limit: bool
    watchdog_limit_seconds: float
    watchdog_killed: bool
    run_error: str | None
    solver_stdout_path: str | None
    solver_stderr_path: str | None
    hard_feasible: bool | None
    cost: float | int | None
    reported_cost: float | int | None
    fresh_cost: float | int | None
    reference_cost: float | int | None
    quality_ratio: float | None
    validation_error: str | None
    solution_artifact: str | None
    native_fields: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        row = {
            "benchmark_name": self.benchmark_name,
            "benchmark_category": self.benchmark_category,
            "dataset": self.dataset,
            "dataset_set": self.dataset_set,
            "instance": self.instance,
            "instance_size": self.instance_size,
            "solver": self.solver,
            "solver_version": self.solver_version,
            "time_limit_seconds": self.time_limit_seconds,
            "actual_time_seconds": self.actual_time_seconds,
            "overshoot_seconds": self.overshoot_seconds,
            "overshoot_ratio": self.overshoot_ratio,
            "wall_time_over_limit": self.wall_time_over_limit,
            "watchdog_limit_seconds": self.watchdog_limit_seconds,
            "watchdog_killed": self.watchdog_killed,
            "run_error": self.run_error,
            "solver_stdout_path": self.solver_stdout_path,
            "solver_stderr_path": self.solver_stderr_path,
            "hard_feasible": self.hard_feasible,
            "cost": self.cost,
            "reported_cost": self.reported_cost,
            "fresh_cost": self.fresh_cost,
            "reference_cost": self.reference_cost,
            "quality_ratio": self.quality_ratio,
            "validation_error": self.validation_error,
            "solution_artifact": self.solution_artifact,
        }
        row.update(self.native_fields)
        return row


class BenchmarkSpec(Protocol):
    name: str
    category: str
    default_solvers: list[str]
    default_time_limits: list[int]
    available_solvers: list[str]
    native_columns: list[str]
    solution_model: type

    def configure_parser(self, parser: Any) -> None: ...

    def cases(self, args: Any) -> Iterable[BenchmarkCase]: ...

    def create_solver(
        self, method: str, time_limit: int
    ) -> Callable[[Any, int], Any]: ...

    def solver_versions(self, solvers: Iterable[str]) -> dict[str, SolverVersion]: ...

    def evaluate(
        self,
        *,
        case: BenchmarkCase,
        run: SolverRun,
        artifact_dir: Path,
    ) -> Evaluation: ...

    def output_path(self, args: Any, run_stamp: str) -> Path: ...

    def artifact_dir(self, args: Any, run_stamp: str) -> Path: ...
