"""CVRP benchmark spec for the shared SolverForge benchmark framework."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import vrplib

from cvrp_bench.domain.models import Instance, Solution
from cvrp_bench.domain.utils import validate
from cvrp_bench.solver.solver import AVAILABLE_METHODS, create_solver
from solverforge_bench.model import BenchmarkCase, Evaluation, SolverRun


class CvrpSpec:
    name = "cvrp"
    category = "list_variable"
    default_solvers = ["timefold_java", "pyvrp", "solverforge"]
    default_time_limits = [1, 10, 60]
    available_solvers = AVAILABLE_METHODS
    native_columns: list[str] = []
    solution_model = Solution

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--num-instances",
            type=int,
            default=None,
            help="Limit the number of CVRPLIB-X instances for a smoke run.",
        )

    def cases(self, args: argparse.Namespace) -> Iterable[BenchmarkCase]:
        data_dir = Path(args.benchmark_root) / "data" / "X"
        instance_names = sorted(
            {
                path.stem
                for path in data_dir.iterdir()
                if path.suffix in {".vrp", ".sol"}
            }
        )
        selected = (
            instance_names[: args.num_instances]
            if args.num_instances
            else instance_names
        )
        for name in selected:
            instance = Instance.model_validate(
                vrplib.read_instance(str(data_dir / f"{name}.vrp"))
            )
            reference = Solution.model_validate(
                vrplib.read_solution(str(data_dir / f"{name}.sol"))
            )
            yield BenchmarkCase(
                dataset="CVRPLIB-X",
                dataset_set="canonical",
                instance=instance.name,
                instance_size=len(instance.demand),
                payload=instance,
                reference_solution=reference,
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
        try:
            validate(solution=solution, instance=case.payload)
        except Exception as exc:
            return Evaluation(
                hard_feasible=False,
                cost=getattr(solution, "cost", None),
                reference_cost=getattr(reference, "cost", None),
                validation_error=f"{exc.__class__.__name__}: {exc}",
            )

        reference_cost = reference.cost if reference else None
        quality_ratio = (
            float(solution.cost / reference_cost) if reference_cost else None
        )
        return Evaluation(
            hard_feasible=True,
            cost=solution.cost,
            reported_cost=solution.cost,
            fresh_cost=solution.cost,
            reference_cost=reference_cost,
            quality_ratio=quality_ratio,
            validation_error="",
        )

    def output_path(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return Path(args.benchmark_root) / "data" / f"benchmark_cvrp_{run_stamp}.csv"

    def artifact_dir(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return Path(args.benchmark_root) / "data" / "artifacts" / f"cvrp_{run_stamp}"


SPEC = CvrpSpec()
