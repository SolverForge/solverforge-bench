from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from job_shop_bench.domain.models import Solution
from job_shop_bench.loader import dataset_group_names, instance_metadata, load_instance
from job_shop_bench.solver.solver import AVAILABLE_METHODS, create_solver, solver_versions
from job_shop_bench.validation import ValidationError, validate
from solverforge_bench.model import BenchmarkCase, Evaluation, SolverRun, SolverVersion


class JobShopSpec:
    name = "job-shop-scheduling"
    category = "scalar_variable"
    default_time_limits = [1, 10, 60]
    available_solvers = AVAILABLE_METHODS
    default_solvers = AVAILABLE_METHODS
    native_columns = ["num_jobs", "num_machines", "num_operations", "source_family", "known_best_makespan", "makespan_gap_to_best"]
    solution_model = Solution

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--dataset-set", default=None)
        parser.add_argument("--datasets", nargs="+", default=None)

    def cases(self, args: argparse.Namespace) -> Iterable[BenchmarkCase]:
        data_dir = Path(args.benchmark_root) / "data" / "jsplib"
        meta = instance_metadata(data_dir)
        selected = list(meta)
        if args.dataset_set:
            allowed = dataset_group_names(data_dir, args.dataset_set)
            selected = [n for n in selected if n in allowed]
        if args.datasets:
            wanted = set(args.datasets)
            selected = [n for n in selected if n in wanted]
        dataset_set = args.dataset_set or ("custom" if args.datasets else "all")
        for name in selected:
            m = meta[name]
            instance = load_instance(data_dir / m["path"], name=name, family=m["family"])
            yield BenchmarkCase(dataset="JSPLIB", dataset_set=dataset_set, instance=name, instance_size=instance.num_jobs * instance.num_machines, payload=instance, native_fields={"num_jobs": instance.num_jobs, "num_machines": instance.num_machines, "num_operations": sum(len(j) for j in instance.operations_by_job), "source_family": instance.family, "known_best_makespan": m.get("known_best_makespan")})

    def create_solver(self, method: str, *, time_limit: int = 60):
        return create_solver(method=method, time_limit=time_limit)

    def solver_versions(self, solvers: Iterable[str]) -> dict[str, SolverVersion]:
        return solver_versions(list(solvers))

    def evaluate(self, *, case: BenchmarkCase, run: SolverRun, artifact_dir: Path) -> Evaluation:
        try:
            makespan = validate(case.payload, run.solution)
        except ValidationError as exc:
            return Evaluation(hard_feasible=False, validation_error=str(exc))
        best = case.native_fields.get("known_best_makespan")
        gap = ((makespan - best) / best) if best else None
        return Evaluation(hard_feasible=True, cost=makespan, reported_cost=getattr(run.solution, "reported_makespan", None), validation_error="", native_fields={"makespan_gap_to_best": gap})

    def output_path(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return Path(args.benchmark_root) / "data" / f"benchmark_job_shop_scheduling_{run_stamp}.csv"

    def artifact_dir(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return Path(args.benchmark_root) / "data" / "artifacts" / f"job_shop_scheduling_{run_stamp}"


SPEC = JobShopSpec()
