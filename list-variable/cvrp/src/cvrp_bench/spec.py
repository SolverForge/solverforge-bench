"""CVRP benchmark spec for the shared SolverForge benchmark framework."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import vrplib

from cvrp_bench.domain.models import Instance, Solution
from cvrp_bench.domain.utils import CvrpValidationError, validate
from cvrp_bench.solver.solver import (
    AVAILABLE_METHODS,
    DEFAULT_METHODS,
    create_solver,
    solver_versions,
)
from solverforge_bench.model import BenchmarkCase, Evaluation, SolverRun, SolverVersion
from solverforge_bench.references import reference_for

_CVRPLIB_X_NAME = re.compile(r"^X-n(?P<size>\d+)-k(?P<vehicles>\d+)$")


def _instance_sort_key(name: str) -> tuple[int, int, str]:
    match = _CVRPLIB_X_NAME.match(name)
    if match is None:
        return (10**9, 10**9, name)
    return (int(match.group("size")), int(match.group("vehicles")), name)


class CvrpSpec:
    name = "cvrp"
    category = "list_variable"
    default_solvers = DEFAULT_METHODS
    default_time_limits = [1, 10, 60]
    available_solvers = AVAILABLE_METHODS
    native_columns = [
        "reference_kind",
        "reference_source",
        "reference_revision",
    ]
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
        # Instances come from the .vrp files only: the directory also holds the
        # shipped tours, the pinned catalog, and the official table.
        instance_names = sorted(
            {path.stem for path in data_dir.glob("*.vrp")},
            key=_instance_sort_key,
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
            # The official CVRPLIB value is the reference, not the bundled .sol:
            # a shipped solution route is one feasible tour, while the table
            # states the optimum or the best known bound for the instance.
            reference = reference_for(data_dir, name)
            yield BenchmarkCase(
                dataset="CVRPLIB-X",
                dataset_set="canonical",
                instance=instance.name,
                instance_size=len(instance.demand),
                payload=instance,
                native_fields={
                    "reference_cost": reference.reference_cost,
                    "reference_kind": reference.kind,
                    "reference_source": reference.source_name,
                    "reference_revision": reference.source_revision,
                },
            )

    def create_solver(self, method: str, *, time_limit: int = 60):
        return create_solver(method=method, time_limit=time_limit)

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
        reference_cost = case.native_fields.get("reference_cost")
        reference_kind = case.native_fields.get("reference_kind")
        try:
            validate(solution=solution, instance=case.payload)
        except CvrpValidationError as exc:
            return Evaluation(
                hard_feasible=False,
                cost=getattr(solution, "cost", None),
                reference_cost=reference_cost,
                validation_error=f"{exc.__class__.__name__}: {exc}",
                native_fields={"reference_kind": reference_kind},
            )

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
            validation_error=None,
            native_fields={"reference_kind": reference_kind},
        )

    def output_path(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return Path(args.benchmark_root) / "data" / f"benchmark_cvrp_{run_stamp}.csv"

    def artifact_dir(self, args: argparse.Namespace, run_stamp: str) -> Path:
        return Path(args.benchmark_root) / "data" / "artifacts" / f"cvrp_{run_stamp}"


SPEC = CvrpSpec()
