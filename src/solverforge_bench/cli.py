"""Unified benchmark command line entrypoint."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from solverforge_bench.registry import canonical_specs
from solverforge_bench.runner import run_benchmark


def main(
    argv: list[str] | None = None, *, default_benchmark: str | None = None
) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if default_benchmark and (not argv or argv[0].startswith("-")):
        argv = [default_benchmark, *argv]
    command_args = list(argv)

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run SolverForge benchmark suites.")
    subparsers = parser.add_subparsers(dest="benchmark", required=True)

    shared_parent = argparse.ArgumentParser(add_help=False)
    shared_parent.add_argument(
        "--solver",
        action="append",
        choices=None,
        help="Solver to run. Repeat to include multiple solvers.",
    )
    shared_parent.add_argument(
        "--time-limits",
        nargs="+",
        type=int,
        help=(
            "Benchmark budgets in seconds. These are passed to solvers, "
            "not used as hard kill deadlines."
        ),
    )
    shared_parent.add_argument(
        "--wall-time-tolerance",
        type=float,
        default=1.1,
        help="Flag wall_time_over_limit when actual time exceeds time_limit * tolerance.",
    )
    shared_parent.add_argument(
        "--watchdog-multiplier",
        type=float,
        default=1.25,
        help="Watchdog containment multiplier applied to the nominal budget.",
    )
    shared_parent.add_argument(
        "--watchdog-grace-seconds",
        type=float,
        default=5.0,
        help="Minimum watchdog grace above the nominal budget.",
    )
    shared_parent.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path. Defaults to the benchmark data directory.",
    )
    shared_parent.add_argument(
        "--run-kind",
        choices=["quick", "candidate", "tag"],
        default="candidate",
        help="Catalog label for this benchmark run.",
    )
    shared_parent.add_argument(
        "--release-tag",
        default=None,
        help="SolverForge release tag for run-kind=tag snapshots.",
    )
    shared_parent.add_argument(
        "--save-postgres",
        action="store_true",
        help="Persist benchmark run metadata and result rows to PostgreSQL.",
    )
    shared_parent.add_argument(
        "--postgres-url",
        default=None,
        help=(
            "PostgreSQL connection URL. Also enables PostgreSQL saving. "
            "Defaults to BENCH_DATABASE_URL, DATABASE_URL, or local postgres."
        ),
    )

    for spec in canonical_specs():
        subparser = subparsers.add_parser(
            spec.name,
            parents=[shared_parent],
            help=f"Run the {spec.name} benchmark.",
        )
        spec.configure_parser(subparser)
        subparser.set_defaults(spec=spec)

    args = parser.parse_args(argv)
    args.argv = command_args
    args.run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.repo_root = repo_root
    args.benchmark_root = _benchmark_root(repo_root, args.spec.name)
    args.save_postgres = args.save_postgres or bool(args.postgres_url)
    _validate_solvers(args)
    _validate_run_catalog(args)
    output_path = run_benchmark(args.spec, args)
    print(output_path)
    if getattr(args, "postgres_run_id", None):
        print(f"postgres_run_id={args.postgres_run_id}")


def _benchmark_root(repo_root: Path, benchmark_name: str) -> Path:
    if benchmark_name == "cvrp":
        return repo_root / "list-variable" / "cvrp"
    if benchmark_name == "employee-scheduling":
        return repo_root / "scalar-variable" / "employee-scheduling"
    raise ValueError(f"Unknown benchmark: {benchmark_name}")


def _validate_solvers(args: argparse.Namespace) -> None:
    if not args.solver:
        return
    invalid = [
        solver for solver in args.solver if solver not in args.spec.available_solvers
    ]
    if invalid:
        available = ", ".join(args.spec.available_solvers)
        raise SystemExit(
            f"Unknown solver(s): {', '.join(invalid)}. Available: {available}"
        )


def _validate_run_catalog(args: argparse.Namespace) -> None:
    if args.run_kind == "tag" and not args.release_tag:
        raise SystemExit("--release-tag is required when --run-kind tag is used.")
    if args.run_kind != "tag" and args.release_tag:
        raise SystemExit("--release-tag is only valid with --run-kind tag.")


if __name__ == "__main__":
    main()
