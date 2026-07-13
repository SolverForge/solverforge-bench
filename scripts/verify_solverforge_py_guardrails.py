#!/usr/bin/env python3.14
"""Run solverforge-py benchmark guardrails and validate their CSV output."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import subprocess
import sys
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass
from importlib import metadata as importlib_metadata
from itertools import product
from pathlib import Path

from _venv_bootstrap import ensure_repo_venv
from verify_solverforge_config_parity import verify_solverforge_config_parity


REPO_ROOT = Path(__file__).resolve().parents[1]
ensure_repo_venv(REPO_ROOT)

from solverforge_bench.redaction import redact_sensitive_command_args  # noqa: E402

DEFAULT_OUTPUT_DIR = REPO_ROOT / "build" / "solverforge-py-guardrails"
SMOKE_TIME_LIMITS = (1, 10)
COMPARISON_CVRP_TIME_LIMITS = (1, 10)
COMPARISON_EMPLOYEE_TIME_LIMITS = (10, 60)
COMPARISON_JSSP_TIME_LIMITS = (1, 10)
SMOKE_EMPLOYEE_DATASETS = ("n005w4",)
COMPARISON_EMPLOYEE_DATASETS = ("n005w4", "n012w8", "n021w4")
COMPARISON_JSSP_DATASETS = ("ft06", "la01", "abz5", "ft10")
JSSP_QUICK_COST_INSTANCES = {"ft06", "la01"}
_CVRPLIB_X_NAME = re.compile(r"^X-n(?P<size>\d+)-k(?P<vehicles>\d+)$")


@dataclass(frozen=True)
class RunRecord:
    phase: str
    benchmark: str
    label: str
    output: str
    command: list[str]


@dataclass(frozen=True, order=True)
class MatrixKey:
    benchmark_name: str
    instance: str
    solver: str
    time_limit_seconds: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MatrixExpectation:
    benchmark_name: str
    instances: tuple[str, ...]
    solvers: tuple[str, ...]
    time_limits: tuple[int, ...]
    requested_dataset_selectors: tuple[str, ...] = ()


class GuardrailInputError(ValueError):
    """Raised when a requested guardrail matrix cannot be resolved exactly."""


class BenchmarkCommandError(RuntimeError):
    """A failed child command with report-safe command arguments."""

    def __init__(self, returncode: int, command: list[str]) -> None:
        self.returncode = returncode
        self.command = command
        super().__init__(f"benchmark command exited {returncode}: {' '.join(command)}")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify solverforge-py benchmark adapter guardrails."
    )
    parser.add_argument(
        "--mode",
        choices=("smoke", "comparison", "release"),
        default="smoke",
        help="Guardrail scope to run.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for guardrail CSVs and summary.json.",
    )
    parser.add_argument(
        "--time-limits",
        nargs="+",
        type=positive_int,
        default=None,
        help="Override benchmark time limits for every guardrail run.",
    )
    parser.add_argument(
        "--employee-datasets",
        nargs="+",
        default=None,
        help="Override employee-scheduling datasets for smoke/comparison runs.",
    )
    parser.add_argument(
        "--jssp-datasets",
        nargs="+",
        default=None,
        help="Override JSSP datasets. Smoke uses the quick group when unset.",
    )
    parser.add_argument(
        "--cvrp-num-instances",
        type=positive_int,
        default=3,
        help="Number of sorted CVRPLIB-X instances to run.",
    )
    parser.add_argument(
        "--save-postgres",
        action="store_true",
        help="Persist guardrail runs to PostgreSQL. Disabled by default.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL URL to use with --save-postgres.",
    )
    parser.add_argument("--max-cvrp-py-rust-ratio", type=float, default=None)
    parser.add_argument("--max-employee-py-rust-ratio", type=float, default=None)
    parser.add_argument("--max-jssp-py-rust-ratio", type=float, default=None)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {
        "mode": args.mode,
        "output_dir": str(args.output_dir),
        "package": {},
        "runs": [],
        "row_counts": {},
        "matrix_coverage": {},
        "comparison_summaries": {},
        "warnings": [],
        "failures": [],
    }
    warnings: list[str] = []
    failures: list[str] = []
    run_records: list[RunRecord] = []

    if args.database_url and not args.save_postgres:
        failures.append("--database-url requires --save-postgres")
    failures.extend(validate_unique_requested_values(args))

    config_failures = verify_solverforge_config_parity()
    summary["config_parity"] = {"failures": config_failures}
    failures.extend(config_failures)

    package_info, package_failures = verify_solverforge_package()
    summary["package"] = package_info
    failures.extend(package_failures)

    if not failures:
        try:
            if args.mode in {"smoke", "release"}:
                run_smoke_guardrails(
                    args, package_info["version"], run_records, summary, failures
                )
            if not failures and args.mode in {"comparison", "release"}:
                run_comparison_guardrails(
                    args,
                    package_info["version"],
                    run_records,
                    summary,
                    warnings,
                    failures,
                )
        except GuardrailInputError as exc:
            failures.append(str(exc))
        except BenchmarkCommandError as exc:
            failures.append(str(exc))
        except subprocess.CalledProcessError as exc:
            command = exc.cmd if isinstance(exc.cmd, list | tuple) else [exc.cmd]
            safe_command = redact_sensitive_command_args(command)
            failures.append(
                f"benchmark command exited {exc.returncode}: {' '.join(safe_command)}"
            )

    summary["runs"] = [asdict(record) for record in run_records]
    summary["warnings"] = warnings
    summary["failures"] = failures
    summary_path = args.output_dir / "summary.json"
    write_summary(summary_path, summary)

    for warning in warnings:
        print(f"guardrail warning: {warning}", file=sys.stderr)
    if failures:
        for failure in failures:
            print(f"guardrail failure: {failure}", file=sys.stderr)
        print(f"summary={summary_path}", file=sys.stderr)
        raise SystemExit(1)

    print("solverforge-py guardrails passed")
    print(f"summary={summary_path}")


def verify_solverforge_package() -> tuple[dict[str, object], list[str]]:
    failures: list[str] = []
    info: dict[str, object] = {}
    try:
        distribution = importlib_metadata.distribution("solverforge")
    except importlib_metadata.PackageNotFoundError:
        return {}, [
            "solverforge Python distribution is not installed in the bench .venv"
        ]

    version = distribution.version
    info["version"] = version
    print(f"solverforge Python package version: {version}", flush=True)

    expected_version = read_solverforge_requirement(REPO_ROOT / "pyproject.toml")
    info["expected_version"] = expected_version
    if version != expected_version:
        failures.append(
            f"installed solverforge version {version!r} does not match "
            f"the benchmark requirement {expected_version!r}"
        )
    if distribution.read_text("direct_url.json"):
        failures.append(
            "installed solverforge is a direct-URL or editable package; "
            "install the exact published wheel with make install-python-deps"
        )
    return info, failures


def read_solverforge_requirement(pyproject: Path) -> str:
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    try:
        dependencies = data["project"]["dependencies"]
    except KeyError as exc:
        raise SystemExit(f"{pyproject} is missing [project].dependencies") from exc
    if not isinstance(dependencies, list):
        raise SystemExit(f"{pyproject} has invalid [project].dependencies")
    requirements = [
        dependency.removeprefix("solverforge==")
        for dependency in dependencies
        if isinstance(dependency, str) and dependency.startswith("solverforge==")
    ]
    if len(requirements) != 1 or not requirements[0]:
        raise SystemExit(
            f"{pyproject} must declare exactly one solverforge==<version> dependency"
        )
    return requirements[0]


def validate_unique_requested_values(args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    for option, values in (
        ("--time-limits", args.time_limits),
        ("--employee-datasets", args.employee_datasets),
        ("--jssp-datasets", args.jssp_datasets),
    ):
        if not values:
            continue
        duplicates = sorted(
            {value for value in values if values.count(value) > 1}, key=str
        )
        if duplicates:
            failures.append(f"{option} contains duplicate values: {duplicates}")
    return failures


def resolve_cvrp_instances(num_instances: int) -> tuple[str, ...]:
    data_dir = REPO_ROOT / "list-variable" / "cvrp" / "data" / "X"
    instance_names = sorted(
        {path.stem for path in data_dir.iterdir() if path.suffix in {".vrp", ".sol"}},
        key=cvrp_instance_sort_key,
    )
    selected = tuple(instance_names[:num_instances])
    if len(selected) != num_instances:
        raise GuardrailInputError(
            "CVRP guardrail requested "
            f"{num_instances} instances, but only {len(instance_names)} are available"
        )
    return selected


def cvrp_instance_sort_key(name: str) -> tuple[int, int, str]:
    match = _CVRPLIB_X_NAME.match(name)
    if match is None:
        return (10**9, 10**9, name)
    return (int(match.group("size")), int(match.group("vehicles")), name)


def resolve_employee_instances(selectors: tuple[str, ...]) -> tuple[str, ...]:
    from employee_scheduling_bench.loader import enumerate_instances

    data_dir = REPO_ROOT / "scalar-variable" / "employee-scheduling" / "data" / "inrc2"
    available = tuple(str(item["name"]) for item in enumerate_instances(str(data_dir)))
    missing = [
        selector
        for selector in selectors
        if not any(name.startswith(selector) for name in available)
    ]
    if missing:
        raise GuardrailInputError(
            "employee-scheduling requested dataset selector(s) matched no "
            f"instances: {missing}"
        )
    return tuple(
        name
        for name in available
        if any(name.startswith(selector) for selector in selectors)
    )


def resolve_jssp_instances(selectors: tuple[str, ...]) -> tuple[str, ...]:
    from job_shop_bench.loader import instance_metadata

    data_dir = REPO_ROOT / "scalar-variable" / "job-shop-scheduling" / "data" / "jsplib"
    available = tuple(instance_metadata(data_dir))
    missing = [selector for selector in selectors if selector not in available]
    if missing:
        raise GuardrailInputError(f"JSSP requested dataset(s) do not exist: {missing}")
    wanted = set(selectors)
    return tuple(name for name in available if name in wanted)


def resolve_jssp_group(group: str) -> tuple[str, ...]:
    from job_shop_bench.loader import dataset_group_names, instance_metadata

    data_dir = REPO_ROOT / "scalar-variable" / "job-shop-scheduling" / "data" / "jsplib"
    available = tuple(instance_metadata(data_dir))
    selected = dataset_group_names(data_dir, group)
    missing = sorted(selected.difference(available))
    if missing:
        raise GuardrailInputError(
            f"JSSP dataset set {group!r} references missing instances: {missing}"
        )
    return tuple(name for name in available if name in selected)


def command_values(values: tuple[int, ...]) -> list[str]:
    return [str(value) for value in values]


def run_smoke_guardrails(
    args: argparse.Namespace,
    installed_version: object,
    run_records: list[RunRecord],
    summary: dict[str, object],
    failures: list[str],
) -> None:
    time_limits = tuple(args.time_limits or SMOKE_TIME_LIMITS)
    employee_datasets = tuple(args.employee_datasets or SMOKE_EMPLOYEE_DATASETS)
    jssp_datasets = (
        tuple(args.jssp_datasets) if args.jssp_datasets else resolve_jssp_group("quick")
    )
    expectations = {
        "cvrp": MatrixExpectation(
            benchmark_name="cvrp",
            instances=resolve_cvrp_instances(args.cvrp_num_instances),
            solvers=("solverforge-py",),
            time_limits=time_limits,
        ),
        "employee-scheduling": MatrixExpectation(
            benchmark_name="employee-scheduling",
            instances=resolve_employee_instances(employee_datasets),
            solvers=("solverforge-py",),
            time_limits=time_limits,
            requested_dataset_selectors=employee_datasets,
        ),
        "job-shop-scheduling": MatrixExpectation(
            benchmark_name="job-shop-scheduling",
            instances=(
                resolve_jssp_instances(jssp_datasets)
                if args.jssp_datasets
                else jssp_datasets
            ),
            solvers=("solverforge-py",),
            time_limits=time_limits,
            requested_dataset_selectors=jssp_datasets,
        ),
    }

    cvrp = run_benchmark(
        args,
        phase="smoke",
        benchmark="cvrp",
        label="CVRP solverforge-py smoke",
        output_name="smoke_cvrp_solverforge_py.csv",
        benchmark_args=[
            "cvrp",
            "--run-kind",
            "quick",
            "--solver",
            "solverforge-py",
            "--num-instances",
            str(args.cvrp_num_instances),
            "--time-limits",
            *command_values(time_limits),
        ],
        run_records=run_records,
    )
    employee = run_benchmark(
        args,
        phase="smoke",
        benchmark="employee-scheduling",
        label="employee solverforge-py smoke",
        output_name="smoke_employee_solverforge_py.csv",
        benchmark_args=[
            "employee-scheduling",
            "--run-kind",
            "quick",
            "--solver",
            "solverforge-py",
            "--datasets",
            *employee_datasets,
            "--time-limits",
            *command_values(time_limits),
        ],
        run_records=run_records,
    )
    jssp_args = [
        "job-shop-scheduling",
        "--run-kind",
        "quick",
        "--solver",
        "solverforge-py",
    ]
    if args.jssp_datasets:
        jssp_args.extend(["--datasets", *args.jssp_datasets])
    else:
        jssp_args.extend(["--dataset-set", "quick"])
    jssp_args.extend(["--time-limits", *command_values(time_limits)])
    jssp = run_benchmark(
        args,
        phase="smoke",
        benchmark="job-shop-scheduling",
        label="JSSP solverforge-py smoke",
        output_name="smoke_job_shop_solverforge_py.csv",
        benchmark_args=jssp_args,
        run_records=run_records,
    )

    smoke_runs = [
        (expectations["cvrp"], "CVRP solverforge-py smoke", cvrp),
        (
            expectations["employee-scheduling"],
            "employee solverforge-py smoke",
            employee,
        ),
        (
            expectations["job-shop-scheduling"],
            "JSSP solverforge-py smoke",
            jssp,
        ),
    ]
    row_counts = summary.setdefault("row_counts", {})
    coverage_summaries = summary.setdefault("matrix_coverage", {})
    assert isinstance(row_counts, dict)
    assert isinstance(coverage_summaries, dict)
    for expectation, label, path in smoke_runs:
        rows = read_rows(path)
        row_counts[label] = len(rows)
        failures.extend(validate_common_rows(rows, label, installed_version))
        failures.extend(validate_smoke_rows(rows, label, expectation.benchmark_name))
        coverage, coverage_failures = validate_matrix_coverage(rows, label, expectation)
        coverage_summaries[label] = coverage
        failures.extend(coverage_failures)


def run_comparison_guardrails(
    args: argparse.Namespace,
    installed_version: object,
    run_records: list[RunRecord],
    summary: dict[str, object],
    warnings: list[str],
    failures: list[str],
) -> None:
    employee_datasets = tuple(args.employee_datasets or COMPARISON_EMPLOYEE_DATASETS)
    jssp_datasets = tuple(args.jssp_datasets or COMPARISON_JSSP_DATASETS)
    cvrp_time_limits = tuple(args.time_limits or COMPARISON_CVRP_TIME_LIMITS)
    employee_time_limits = tuple(args.time_limits or COMPARISON_EMPLOYEE_TIME_LIMITS)
    jssp_time_limits = tuple(args.time_limits or COMPARISON_JSSP_TIME_LIMITS)
    pair_solvers = ("solverforge", "solverforge-py")
    expectations = {
        "cvrp": MatrixExpectation(
            benchmark_name="cvrp",
            instances=resolve_cvrp_instances(args.cvrp_num_instances),
            solvers=pair_solvers,
            time_limits=cvrp_time_limits,
        ),
        "employee-scheduling": MatrixExpectation(
            benchmark_name="employee-scheduling",
            instances=resolve_employee_instances(employee_datasets),
            solvers=pair_solvers,
            time_limits=employee_time_limits,
            requested_dataset_selectors=employee_datasets,
        ),
        "job-shop-scheduling": MatrixExpectation(
            benchmark_name="job-shop-scheduling",
            instances=resolve_jssp_instances(jssp_datasets),
            solvers=pair_solvers,
            time_limits=jssp_time_limits,
            requested_dataset_selectors=jssp_datasets,
        ),
    }

    comparison_runs = [
        (
            expectations["cvrp"],
            "CVRP solverforge native/Python comparison",
            run_benchmark(
                args,
                phase="comparison",
                benchmark="cvrp",
                label="CVRP solverforge native/Python comparison",
                output_name="comparison_cvrp_solverforge_pair.csv",
                benchmark_args=[
                    "cvrp",
                    "--run-kind",
                    "candidate",
                    "--solver",
                    "solverforge",
                    "--solver",
                    "solverforge-py",
                    "--num-instances",
                    str(args.cvrp_num_instances),
                    "--time-limits",
                    *command_values(cvrp_time_limits),
                ],
                run_records=run_records,
            ),
            args.max_cvrp_py_rust_ratio,
        ),
        (
            expectations["employee-scheduling"],
            "employee solverforge native/Python comparison",
            run_benchmark(
                args,
                phase="comparison",
                benchmark="employee-scheduling",
                label="employee solverforge native/Python comparison",
                output_name="comparison_employee_solverforge_pair.csv",
                benchmark_args=[
                    "employee-scheduling",
                    "--run-kind",
                    "candidate",
                    "--solver",
                    "solverforge",
                    "--solver",
                    "solverforge-py",
                    "--datasets",
                    *employee_datasets,
                    "--time-limits",
                    *command_values(employee_time_limits),
                ],
                run_records=run_records,
            ),
            args.max_employee_py_rust_ratio,
        ),
        (
            expectations["job-shop-scheduling"],
            "JSSP solverforge native/Python comparison",
            run_benchmark(
                args,
                phase="comparison",
                benchmark="job-shop-scheduling",
                label="JSSP solverforge native/Python comparison",
                output_name="comparison_job_shop_solverforge_pair.csv",
                benchmark_args=[
                    "job-shop-scheduling",
                    "--run-kind",
                    "candidate",
                    "--solver",
                    "solverforge",
                    "--solver",
                    "solverforge-py",
                    "--datasets",
                    *jssp_datasets,
                    "--time-limits",
                    *command_values(jssp_time_limits),
                ],
                run_records=run_records,
            ),
            args.max_jssp_py_rust_ratio,
        ),
    ]

    row_counts = summary.setdefault("row_counts", {})
    coverage_summaries = summary.setdefault("matrix_coverage", {})
    comparison_summaries = summary.setdefault("comparison_summaries", {})
    assert isinstance(row_counts, dict)
    assert isinstance(coverage_summaries, dict)
    assert isinstance(comparison_summaries, dict)
    for expectation, label, path, max_cost_ratio in comparison_runs:
        rows = read_rows(path)
        row_counts[label] = len(rows)
        failures.extend(validate_common_rows(rows, label, installed_version))
        coverage, coverage_failures = validate_matrix_coverage(rows, label, expectation)
        coverage_summaries[label] = coverage
        failures.extend(coverage_failures)
        comparison = summarize_comparison_rows(rows, label)
        comparison_summaries[expectation.benchmark_name] = comparison
        print_comparison_summary(label, comparison)
        failures.extend(pairing_failures(label, comparison))
        threshold_failures, threshold_warnings = check_cost_ratio_threshold(
            label, comparison, max_cost_ratio
        )
        failures.extend(threshold_failures)
        warnings.extend(threshold_warnings)


def run_benchmark(
    args: argparse.Namespace,
    *,
    phase: str,
    benchmark: str,
    label: str,
    output_name: str,
    benchmark_args: list[str],
    run_records: list[RunRecord],
) -> Path:
    output_path = args.output_dir / output_name
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_benchmark.py"),
        *benchmark_args,
        "--output",
        str(output_path),
        "--log-dir",
        str(args.output_dir / "logs"),
    ]
    if args.save_postgres:
        command.append("--save-postgres")
        if args.database_url:
            command.extend(["--postgres-url", args.database_url])
    else:
        command.append("--no-save-postgres")

    safe_command = redact_sensitive_command_args(command)
    try:
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        raise BenchmarkCommandError(exc.returncode, safe_command) from None
    run_records.append(
        RunRecord(
            phase=phase,
            benchmark=benchmark,
            label=label,
            output=str(output_path),
            command=safe_command,
        )
    )
    return output_path


def validate_matrix_coverage(
    rows: list[dict[str, str]],
    label: str,
    expectation: MatrixExpectation,
) -> tuple[dict[str, object], list[str]]:
    expected_keys = {
        MatrixKey(
            benchmark_name=expectation.benchmark_name,
            instance=instance,
            solver=solver,
            time_limit_seconds=str(time_limit),
        )
        for instance, solver, time_limit in product(
            expectation.instances,
            expectation.solvers,
            expectation.time_limits,
        )
    }
    actual_counts = Counter(
        MatrixKey(
            benchmark_name=row.get("benchmark_name", ""),
            instance=row.get("instance", ""),
            solver=row.get("solver", ""),
            time_limit_seconds=row.get("time_limit_seconds", ""),
        )
        for row in rows
    )
    actual_keys = set(actual_counts)
    missing = [key.as_dict() for key in sorted(expected_keys - actual_keys)]
    unexpected = [key.as_dict() for key in sorted(actual_keys - expected_keys)]
    duplicates = [
        key.as_dict() | {"count": count}
        for key, count in sorted(actual_counts.items())
        if count != 1
    ]
    coverage: dict[str, object] = {
        "benchmark_name": expectation.benchmark_name,
        "requested_dataset_selectors": list(expectation.requested_dataset_selectors),
        "expected_instances": list(expectation.instances),
        "expected_solvers": list(expectation.solvers),
        "expected_time_limits_seconds": list(expectation.time_limits),
        "expected_row_count": len(expected_keys),
        "observed_row_count": len(rows),
        "missing_row_keys": missing,
        "unexpected_row_keys": unexpected,
        "duplicate_row_keys": duplicates,
        "complete": not missing and not unexpected and not duplicates,
    }
    failures: list[str] = []
    if missing:
        failures.append(f"{label} is missing requested matrix rows: {missing}")
    if unexpected:
        failures.append(f"{label} has unexpected matrix rows: {unexpected}")
    if duplicates:
        failures.append(f"{label} has duplicate matrix rows: {duplicates}")
    return coverage, failures


def validate_common_rows(
    rows: list[dict[str, str]], label: str, installed_version: object
) -> list[str]:
    if not rows:
        return [f"{label} produced no rows"]
    failures = []
    for row in rows:
        row_label = (
            f"{label} {row.get('instance', '')} "
            f"{row.get('solver', '')} {row.get('time_limit_seconds', '')}s"
        )
        if not is_true(row.get("fair_start_valid", "")):
            failures.append(f"{row_label} fair-start witness invalid")
        if row.get("run_error", ""):
            failures.append(f"{row_label} run_error={row['run_error']}")
        if row.get("validation_error", ""):
            failures.append(f"{row_label} validation_error={row['validation_error']}")
        if is_true(row.get("watchdog_killed", "")):
            failures.append(f"{row_label} watchdog killed solver")
        if (
            row.get("solver") == "solverforge-py"
            and row.get("solver_version") != installed_version
        ):
            failures.append(
                f"{row_label} solver_version={row.get('solver_version')!r} "
                f"does not match installed solverforge {installed_version!r}"
            )
    return failures


def validate_smoke_rows(
    rows: list[dict[str, str]], label: str, benchmark_name: str
) -> list[str]:
    failures = []
    for row in rows:
        row_label = (
            f"{label} {row.get('instance', '')} {row.get('time_limit_seconds', '')}s"
        )
        if row.get("solver") != "solverforge-py":
            failures.append(f"{row_label} has unexpected solver {row.get('solver')}")
        if benchmark_name in {"cvrp", "employee-scheduling"}:
            if not is_true(row.get("hard_feasible", "")):
                failures.append(f"{row_label} infeasible")
            if row.get("cost", "") == "":
                failures.append(f"{row_label} missing cost")
        if (
            benchmark_name == "job-shop-scheduling"
            and row.get("instance") in JSSP_QUICK_COST_INSTANCES
        ):
            if not is_true(row.get("hard_feasible", "")):
                failures.append(f"{row_label} infeasible")
            if row.get("cost", "") == "":
                failures.append(f"{row_label} missing cost")
    return failures


def summarize_comparison_rows(
    rows: list[dict[str, str]], label: str
) -> dict[str, object]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (
            row.get("benchmark_name", ""),
            row.get("instance", ""),
            row.get("time_limit_seconds", ""),
        )
        grouped.setdefault(key, []).append(row)

    missing_pair_keys: list[dict[str, str]] = []
    duplicate_pair_keys: list[dict[str, str]] = []
    cost_ratios: list[float] = []
    wall_time_ratios: list[float] = []
    valid_pair_count = 0
    invalid_python_row_count = 0

    for key, group_rows in sorted(grouped.items()):
        native_rows = [row for row in group_rows if row.get("solver") == "solverforge"]
        python_rows = [
            row for row in group_rows if row.get("solver") == "solverforge-py"
        ]
        key_payload = {
            "benchmark_name": key[0],
            "instance": key[1],
            "time_limit_seconds": key[2],
        }
        if len(native_rows) != 1 or len(python_rows) != 1:
            missing_pair_keys.append(key_payload)
            continue
        if len(group_rows) != 2:
            duplicate_pair_keys.append(key_payload)
            continue

        native = native_rows[0]
        python = python_rows[0]
        if not is_valid_python_row(python):
            invalid_python_row_count += 1
        native_cost = parse_float(native.get("cost", ""))
        python_cost = parse_float(python.get("cost", ""))
        native_time = parse_float(native.get("actual_time_seconds", ""))
        python_time = parse_float(python.get("actual_time_seconds", ""))
        if (
            is_true(native.get("hard_feasible", ""))
            and is_true(python.get("hard_feasible", ""))
            and native_cost is not None
            and python_cost is not None
            and native_cost != 0
        ):
            cost_ratios.append(python_cost / native_cost)
            valid_pair_count += 1
        if native_time is not None and python_time is not None and native_time > 0:
            wall_time_ratios.append(python_time / native_time)

    return {
        "label": label,
        "pair_count": len(grouped),
        "valid_pair_count": valid_pair_count,
        "missing_pair_keys": missing_pair_keys,
        "duplicate_pair_keys": duplicate_pair_keys,
        "python_rust_median_cost_ratio": median(cost_ratios),
        "python_rust_average_cost_ratio": average(cost_ratios),
        "python_rust_median_wall_time_ratio": median(wall_time_ratios),
        "invalid_python_row_count": invalid_python_row_count,
    }


def print_comparison_summary(label: str, summary: dict[str, object]) -> None:
    print(
        f"{label}: "
        f"pair_count={summary['pair_count']} "
        f"valid_pair_count={summary['valid_pair_count']} "
        f"python_rust_median_cost_ratio="
        f"{format_optional_ratio(summary['python_rust_median_cost_ratio'])} "
        f"python_rust_average_cost_ratio="
        f"{format_optional_ratio(summary['python_rust_average_cost_ratio'])} "
        f"python_rust_median_wall_time_ratio="
        f"{format_optional_ratio(summary['python_rust_median_wall_time_ratio'])} "
        f"invalid_python_row_count={summary['invalid_python_row_count']}"
    )


def check_cost_ratio_threshold(
    label: str, summary: dict[str, object], max_cost_ratio: float | None
) -> tuple[list[str], list[str]]:
    if max_cost_ratio is None:
        return [], []
    ratio = summary["python_rust_median_cost_ratio"]
    if ratio is None:
        return [f"{label} has no valid Python/Rust cost ratio"], []
    assert isinstance(ratio, float)
    if ratio > max_cost_ratio:
        return [
            f"{label} median Python/Rust cost ratio {ratio:.4g} exceeds "
            f"{max_cost_ratio:.4g}"
        ], []
    return [], []


def pairing_failures(label: str, summary: dict[str, object]) -> list[str]:
    failures = []
    missing = summary["missing_pair_keys"]
    duplicates = summary["duplicate_pair_keys"]
    assert isinstance(missing, list)
    assert isinstance(duplicates, list)
    if missing:
        failures.append(f"{label} has missing native/Python pair keys: {missing}")
    if duplicates:
        failures.append(
            f"{label} has duplicate solver rows for pair keys: {duplicates}"
        )
    return failures


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_summary(path: Path, summary: dict[str, object]) -> None:
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def is_true(value: str) -> bool:
    return value.strip().lower() == "true"


def parse_float(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def is_valid_python_row(row: dict[str, str]) -> bool:
    return (
        is_true(row.get("hard_feasible", ""))
        and row.get("cost", "") != ""
        and row.get("run_error", "") == ""
        and row.get("validation_error", "") == ""
        and not is_true(row.get("watchdog_killed", ""))
    )


def format_optional_ratio(value: object) -> str:
    if value is None:
        return "n/a"
    assert isinstance(value, float)
    return f"{value:.4g}"


if __name__ == "__main__":
    main()
