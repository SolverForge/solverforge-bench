"""Delivery-at-scale benchmark spec for the shared framework."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

from delivery_scale_bench.domain.models import Solution
from delivery_scale_bench.generator import GENERATOR_VERSION
from delivery_scale_bench.loader import group_names, instance_entries, load_instance
from delivery_scale_bench.solver.solver import (
    AVAILABLE_METHODS,
    DEFAULT_METHODS,
    create_solver,
    solver_versions,
)
from delivery_scale_bench.validation import HardConstraintViolation, validate_breakdown
from solverforge_bench.model import BenchmarkCase, Evaluation, SolverRun, SolverVersion

DATASET = "SolverForge delivery-scale synthetic"


class DeliveryScaleSpec:
    name = "delivery-scale"
    category = "huge_scale"
    # One budget: 300 s, where the huge-scale quality gap is measured.
    default_time_limits = [300]
    available_solvers = AVAILABLE_METHODS
    default_solvers = DEFAULT_METHODS
    native_columns = [
        "deliveries",
        "vehicles",
        "generator_version",
        "validator_model_delta",
        "score_drift",
        "unassigned_deliveries",
        "solver_metadata",
    ]
    solution_model = Solution

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dataset-set",
            default=None,
            help="Dataset group from data/deliveries/manifest.json: quick or canonical.",
        )
        parser.add_argument(
            "--datasets",
            nargs="+",
            default=None,
            help="Filter by instance name prefix, e.g. ds-s10000.",
        )

    def cases(self, args: argparse.Namespace) -> Iterable[BenchmarkCase]:
        data_dir = _data_dir(args)
        dataset_set = _dataset_set_label(args)
        for entry in _selected_entries(args):
            instance = load_instance(data_dir, entry)
            yield BenchmarkCase(
                dataset=DATASET,
                dataset_set=dataset_set,
                instance=entry["name"],
                instance_size=len(instance.deliveries),
                payload=instance,
                context=dict(entry),
                native_fields={
                    "deliveries": len(instance.deliveries),
                    "vehicles": instance.vehicle_count,
                    "generator_version": GENERATOR_VERSION,
                },
            )

    def create_solver(self, method: str, *, time_limit: int = 60):
        return create_solver(method, time_limit=time_limit)

    def solver_versions(self, solvers: Iterable[str]) -> dict[str, SolverVersion]:
        return solver_versions(list(solvers))

    def evaluate(
        self,
        *,
        case: BenchmarkCase,
        run: SolverRun,
        artifact_dir: Path,
    ) -> Evaluation:
        solution = run.solution
        assert solution is not None, "the runner evaluates only returned solutions"
        try:
            breakdown = validate_breakdown(solution=solution, instance=case.payload)
        except HardConstraintViolation as exc:
            return Evaluation(
                hard_feasible=False,
                reported_cost=solution.reported_cost,
                fresh_cost=solution.fresh_cost,
                validation_error=f"{exc.__class__.__name__}: {exc}",
                native_fields={
                    "validator_model_delta": None,
                    "score_drift": solution.score_drift,
                    "solver_metadata": solution.solver_metadata,
                },
            )

        validator_cost = sum(breakdown.values())
        solution.validator_cost = validator_cost
        solution.validator_breakdown = breakdown
        model_delta = (
            validator_cost - solution.fresh_cost
            if solution.fresh_cost is not None
            else None
        )
        solution.validator_model_delta = model_delta
        artifact_path = _write_solution_artifact(
            solution,
            artifact_dir=artifact_dir,
            instance_name=case.instance,
            solver_name=run.solver,
            time_limit=run.time_limit_seconds,
        )
        # Synthetic instances have no official reference value, and a
        # solver's own result is never substituted for one: reference_cost and
        # quality_ratio stay empty and rows compare on validator cost.
        return Evaluation(
            hard_feasible=True,
            cost=validator_cost,
            reported_cost=solution.reported_cost,
            fresh_cost=solution.fresh_cost,
            validation_error=None,
            solution_artifact=artifact_path,
            native_fields={
                "validator_model_delta": model_delta,
                "score_drift": solution.score_drift,
                "solver_metadata": solution.solver_metadata,
            },
        )

    def output_path(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return (
            Path(args.benchmark_root)
            / "data"
            / f"benchmark_delivery_scale_{run_stamp}.csv"
        )

    def artifact_dir(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return (
            Path(args.benchmark_root)
            / "data"
            / "artifacts"
            / f"delivery_scale_{run_stamp}"
        )


def _data_dir(args: argparse.Namespace) -> Path:
    return Path(args.benchmark_root) / "data" / "deliveries"


def _selected_entries(args: argparse.Namespace) -> list[dict]:
    data_dir = _data_dir(args)
    entries = instance_entries(data_dir)
    if args.dataset_set:
        names = set(group_names(data_dir, args.dataset_set))
        entries = [entry for entry in entries if entry["name"] in names]
    if args.datasets:
        entries = [
            entry
            for entry in entries
            if any(entry["name"].startswith(prefix) for prefix in args.datasets)
        ]
    return entries


def _dataset_set_label(args: argparse.Namespace) -> str:
    if args.dataset_set:
        return args.dataset_set
    if args.datasets:
        return "custom"
    return "all"


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def _write_solution_artifact(
    solution: Solution,
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
        json.dumps(solution.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    return str(path)


SPEC = DeliveryScaleSpec()
