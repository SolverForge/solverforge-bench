"""Unified benchmark command line entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from solverforge_bench.config import (
    BenchmarkConfigError,
    RUN_KIND_CHOICES,
    apply_benchmark_config,
    config_path_from_argv,
    finalize_benchmark_defaults,
    finalize_run_catalog,
    load_benchmark_config,
)
from solverforge_bench.registry import canonical_specs
from solverforge_bench.runner import run_benchmark
from solverforge_bench.validation import validate_unique_solvers

LOGGER = logging.getLogger(__name__)


def main(
    argv: list[str] | None = None, *, default_benchmark: str | None = None
) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if default_benchmark and (not argv or argv[0].startswith("-")):
        argv = [default_benchmark, *argv]
    command_args = list(argv)

    repo_root = Path(__file__).resolve().parents[2]
    specs = canonical_specs()
    benchmark_names = {spec.name for spec in specs}
    try:
        config = load_benchmark_config(
            config_path_from_argv(argv), benchmark_names=benchmark_names
        )
    except BenchmarkConfigError as exc:
        raise SystemExit(str(exc)) from exc
    if not _benchmark_from_argv(argv, benchmark_names) and config.benchmark:
        argv = [config.benchmark, *argv]

    parser = argparse.ArgumentParser(description="Run SolverForge benchmark suites.")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="TOML benchmark configuration file.",
    )
    subparsers = parser.add_subparsers(dest="benchmark", required=True)

    shared_parent = argparse.ArgumentParser(add_help=False)
    shared_parent.add_argument(
        "--config",
        type=Path,
        default=None,
        help="TOML benchmark configuration file.",
    )
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
        default=None,
        help="Flag wall_time_over_limit when actual time exceeds time_limit * tolerance.",
    )
    shared_parent.add_argument(
        "--watchdog-multiplier",
        type=float,
        default=None,
        help="Watchdog containment multiplier applied to the nominal budget.",
    )
    shared_parent.add_argument(
        "--watchdog-grace-seconds",
        type=float,
        default=None,
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
        choices=RUN_KIND_CHOICES,
        default=None,
        help="Catalog label for this benchmark run.",
    )
    shared_parent.add_argument(
        "--nightly",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Mark this run as a scheduled nightly run.",
    )
    shared_parent.add_argument(
        "--release-tag",
        default=None,
        help="SolverForge release tag for run-kind=tag snapshots.",
    )
    shared_parent.add_argument(
        "--save-postgres",
        action=argparse.BooleanOptionalAction,
        default=None,
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
    shared_parent.add_argument(
        "--log-level",
        default=None,
        help="Benchmark log level. Defaults to INFO.",
    )
    shared_parent.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help=(
            "Parent directory for run-scoped logs. Defaults to "
            "logs/<benchmark>_<run_stamp>/."
        ),
    )
    shared_parent.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Explicit benchmark run log path.",
    )
    shared_parent.add_argument(
        "--show-solver-output",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Mirror solver stdout/stderr to the benchmark console.",
    )
    shared_parent.add_argument(
        "--capture-solver-output",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Write solver stdout/stderr to per-solver log files.",
    )

    for spec in specs:
        subparser = subparsers.add_parser(
            spec.name,
            parents=[shared_parent],
            help=f"Run the {spec.name} benchmark.",
        )
        spec.configure_parser(subparser)
        subparser.set_defaults(spec=spec)

    args = parser.parse_args(argv)
    run_kind_from_cli = args.run_kind is not None
    release_tag_from_cli = args.release_tag is not None
    postgres_url_from_cli = args.postgres_url is not None
    save_postgres_from_cli = args.save_postgres is not None
    apply_benchmark_config(args, config)
    finalize_benchmark_defaults(
        args,
        postgres_url_enables_save=postgres_url_from_cli and not save_postgres_from_cli,
    )
    try:
        finalize_run_catalog(
            args,
            run_kind_from_cli=run_kind_from_cli,
            release_tag_from_cli=release_tag_from_cli,
        )
    except BenchmarkConfigError as exc:
        raise SystemExit(str(exc)) from exc
    args.argv = command_args
    args.run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    args.repo_root = repo_root
    args.benchmark_root = _benchmark_root(repo_root, args.spec.name)
    _validate_solvers(args)
    try:
        output_path = run_benchmark(args.spec, args)
    except Exception:
        LOGGER.exception("benchmark_failed benchmark=%s", args.spec.name)
        raise
    print(output_path)
    if getattr(args, "log_path", None):
        print(f"log_path={args.log_path}")
    if getattr(args, "postgres_run_id", None):
        print(f"postgres_run_id={args.postgres_run_id}")


def _benchmark_root(repo_root: Path, benchmark_name: str) -> Path:
    if benchmark_name == "cvrp":
        return repo_root / "list-variable" / "cvrp"
    if benchmark_name == "employee-scheduling":
        return repo_root / "scalar-variable" / "employee-scheduling"
    raise ValueError(f"Unknown benchmark: {benchmark_name}")


def _benchmark_from_argv(argv: list[str], benchmark_names: set[str]) -> str | None:
    return next((value for value in argv if value in benchmark_names), None)


def _validate_solvers(args: argparse.Namespace) -> None:
    if not args.solver:
        return
    try:
        validate_unique_solvers(args.solver)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    invalid = [
        solver for solver in args.solver if solver not in args.spec.available_solvers
    ]
    if invalid:
        available = ", ".join(args.spec.available_solvers)
        raise SystemExit(
            f"Unknown solver(s): {', '.join(invalid)}. Available: {available}"
        )


if __name__ == "__main__":
    main()
