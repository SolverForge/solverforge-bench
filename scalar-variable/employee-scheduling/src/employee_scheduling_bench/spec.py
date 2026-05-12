"""Employee-scheduling benchmark spec for the shared framework."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

from employee_scheduling_bench.domain.models import Solution
from employee_scheduling_bench.loader import (
    dataset_group_names,
    enumerate_instances,
    load_instance,
    load_solution,
)
from employee_scheduling_bench.solver.solver import create_solver
from employee_scheduling_bench.validation import validate_breakdown
from solverforge_bench.model import BenchmarkCase, Evaluation, SolverRun


class EmployeeSchedulingSpec:
    name = "employee-scheduling"
    category = "scalar_variable"
    default_solvers = ["solverforge", "timefold_java", "ortools"]
    default_time_limits = [1, 10, 60]
    available_solvers = ["solverforge", "timefold_java", "ortools"]
    native_columns = ["nurses", "weeks", "validator_model_delta", "score_drift"]
    solution_model = Solution

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dataset-set",
            default=None,
            help="Dataset group from data/inrc2/manifest.json, e.g. canonical or quick.",
        )
        parser.add_argument(
            "--datasets",
            nargs="+",
            default=None,
            help="Filter by instance group name, e.g. n005w4 n030w4.",
        )

    def cases(self, args: argparse.Namespace) -> Iterable[BenchmarkCase]:
        dataset_set_label = _dataset_set_label(args)
        for inst_info in _selected_instances(args):
            instance = load_instance(
                inst_info["scenario_path"],
                inst_info["history_path"],
                inst_info["week_paths"],
            )
            reference = (
                load_solution(inst_info["solution_dir"])
                if inst_info["solution_dir"]
                else None
            )
            yield BenchmarkCase(
                dataset="INRC-II",
                dataset_set=dataset_set_label,
                instance=inst_info["name"],
                instance_size=inst_info["num_nurses"],
                payload=instance,
                reference_solution=reference,
                context=inst_info,
                native_fields={
                    "nurses": inst_info["num_nurses"],
                    "weeks": inst_info["num_weeks"],
                },
            )

    def create_solver(self, method: str, *, time_limit: int = 60):
        return create_solver(method=method, time_limit=time_limit)

    def evaluate(
        self,
        *,
        case: BenchmarkCase,
        run: SolverRun,
        artifact_dir: Path,
    ) -> Evaluation:
        solution = run.solution
        reference = case.reference_solution
        reference_cost = reference.cost if reference else None
        try:
            breakdown = validate_breakdown(solution=solution, instance=case.payload)
        except Exception as exc:
            return Evaluation(
                hard_feasible=False,
                cost=None,
                reported_cost=getattr(solution, "reported_cost", None),
                fresh_cost=getattr(solution, "fresh_cost", None),
                reference_cost=reference_cost,
                quality_ratio=None,
                validation_error=f"{exc.__class__.__name__}: {exc}",
                native_fields={
                    "validator_model_delta": None,
                    "score_drift": getattr(solution, "score_drift", None),
                },
            )

        validator_cost = sum(breakdown.values())
        solution.validator_cost = validator_cost
        solution.validator_breakdown = breakdown
        reported_cost = solution.reported_cost
        fresh_cost = solution.fresh_cost
        model_cost = fresh_cost if fresh_cost is not None else solution.cost
        model_delta = validator_cost - model_cost
        solution.validator_model_delta = model_delta
        artifact_path = _write_solution_artifact(
            solution,
            artifact_dir=artifact_dir,
            instance_name=case.instance,
            solver_name=run.solver,
            time_limit=run.time_limit_seconds,
        )
        return Evaluation(
            hard_feasible=True,
            cost=validator_cost,
            reported_cost=reported_cost,
            fresh_cost=fresh_cost,
            reference_cost=reference_cost,
            quality_ratio=(
                float(validator_cost / reference_cost)
                if reference_cost and reference_cost > 0
                else None
            ),
            validation_error="",
            solution_artifact=artifact_path,
            native_fields={
                "validator_model_delta": model_delta,
                "score_drift": solution.score_drift,
            },
        )

    def output_path(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return (
            Path(args.benchmark_root)
            / "data"
            / (f"benchmark_employee_scheduling_{run_stamp}.csv")
        )

    def artifact_dir(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return (
            Path(args.benchmark_root)
            / "data"
            / "artifacts"
            / (f"employee_scheduling_{run_stamp}")
        )


def _selected_instances(args: argparse.Namespace) -> list[dict]:
    data_dir = Path(args.benchmark_root) / "data" / "inrc2"
    instances = enumerate_instances(str(data_dir))

    if args.dataset_set:
        dataset_names = dataset_group_names(str(data_dir), args.dataset_set)
        instances = [
            inst
            for inst in instances
            if inst["name"].split("_H", maxsplit=1)[0] in dataset_names
        ]

    if args.datasets:
        instances = [
            inst
            for inst in instances
            if any(inst["name"].startswith(dataset) for dataset in args.datasets)
        ]

    return instances


def _dataset_set_label(args: argparse.Namespace) -> str:
    if args.dataset_set:
        return args.dataset_set
    if args.datasets:
        return "custom"
    return "all"


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def _solution_payload(solution):
    if hasattr(solution, "model_dump"):
        return solution.model_dump(mode="json")
    return solution.dict()


def _write_solution_artifact(
    solution,
    *,
    artifact_dir: Path,
    instance_name: str,
    solver_name: str,
    time_limit: int,
) -> str:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / (
        f"{_safe_name(instance_name)}__{_safe_name(solver_name)}__{time_limit}s.json"
    )
    solution.solution_artifact = str(path)
    path.write_text(
        json.dumps(_solution_payload(solution), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return str(path)


SPEC = EmployeeSchedulingSpec()
