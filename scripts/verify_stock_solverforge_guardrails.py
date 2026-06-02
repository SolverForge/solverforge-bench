#!/usr/bin/env python3.14
"""Run stock SolverForge benchmark guardrails and validate their CSV output."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSSP_SUBSET = ("ft10", "swv20", "yn3", "ta01")
DEFAULT_TIME_LIMITS = ("1", "10")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify stock SolverForge benchmark guardrails."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "build" / "stock-solverforge-guardrails",
    )
    parser.add_argument(
        "--jssp-subset",
        nargs="+",
        default=list(DEFAULT_JSSP_SUBSET),
        help="Canonical JSPLIB instances used as the non-quick JSSP guardrail.",
    )
    parser.add_argument(
        "--time-limits",
        nargs="+",
        default=list(DEFAULT_TIME_LIMITS),
        help="Time limits used for every guardrail run.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    jssp_quick = run_benchmark(
        [
            "job-shop-scheduling",
            "--run-kind",
            "quick",
            "--dataset-set",
            "quick",
            "--time-limits",
            *args.time_limits,
        ],
        args.output_dir / "job_shop_quick.csv",
    )
    jssp_subset = run_benchmark(
        [
            "job-shop-scheduling",
            "--run-kind",
            "candidate",
            "--datasets",
            *args.jssp_subset,
            "--time-limits",
            *args.time_limits,
        ],
        args.output_dir / "job_shop_canonical_subset.csv",
    )
    cvrp_smoke = run_benchmark(
        [
            "cvrp",
            "--run-kind",
            "quick",
            "--solver",
            "solverforge",
            "--num-instances",
            "3",
            "--time-limits",
            *args.time_limits,
        ],
        args.output_dir / "cvrp_solverforge_quick.csv",
    )
    employee_smoke = run_benchmark(
        [
            "employee-scheduling",
            "--run-kind",
            "quick",
            "--solver",
            "solverforge",
            "--datasets",
            "n005w4",
            "--time-limits",
            *args.time_limits,
        ],
        args.output_dir / "employee_solverforge_quick.csv",
    )

    failures: list[str] = []
    failures.extend(validate_jssp_win(jssp_quick, "JSSP quick"))
    failures.extend(validate_jssp_win(jssp_subset, "JSSP canonical subset"))
    failures.extend(validate_solverforge_smoke(cvrp_smoke, "CVRP SolverForge quick"))
    failures.extend(
        validate_solverforge_smoke(employee_smoke, "employee SolverForge quick")
    )

    if failures:
        for failure in failures:
            print(f"guardrail failure: {failure}", file=sys.stderr)
        raise SystemExit(1)

    print("stock SolverForge guardrails passed")
    for path in (jssp_quick, jssp_subset, cvrp_smoke, employee_smoke):
        print(path)


def run_benchmark(args: list[str], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_benchmark.py"),
        *args,
        "--output",
        str(output_path),
    ]
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    return output_path


def validate_jssp_win(path: Path, label: str) -> list[str]:
    rows = read_rows(path)
    failures = validate_common_rows(rows, label)
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["instance"], row["time_limit_seconds"])].append(row)

    for (instance, time_limit), case_rows in sorted(grouped.items()):
        solverforge = [row for row in case_rows if row["solver"] == "solverforge"]
        if len(solverforge) != 1:
            failures.append(
                f"{label} {instance} {time_limit}s expected one SolverForge row"
            )
            continue
        sf = solverforge[0]
        if not is_true(sf["hard_feasible"]):
            failures.append(f"{label} {instance} {time_limit}s SolverForge infeasible")
            continue
        sf_cost = parse_int(sf["cost"])
        if sf_cost is None:
            failures.append(
                f"{label} {instance} {time_limit}s SolverForge missing cost"
            )
            continue
        feasible_costs = [
            parse_int(row["cost"])
            for row in case_rows
            if is_true(row["hard_feasible"]) and parse_int(row["cost"]) is not None
        ]
        if feasible_costs and sf_cost > min(feasible_costs):
            failures.append(
                f"{label} {instance} {time_limit}s SolverForge cost {sf_cost} "
                f"lost to best feasible cost {min(feasible_costs)}"
            )
    return failures


def validate_solverforge_smoke(path: Path, label: str) -> list[str]:
    rows = read_rows(path)
    failures = validate_common_rows(rows, label)
    for row in rows:
        if row["solver"] != "solverforge":
            failures.append(f"{label} has unexpected solver {row['solver']}")
        if not is_true(row["hard_feasible"]):
            failures.append(
                f"{label} {row['instance']} {row['time_limit_seconds']}s infeasible"
            )
    return failures


def validate_common_rows(rows: list[dict[str, str]], label: str) -> list[str]:
    failures = []
    if not rows:
        return [f"{label} produced no rows"]
    for row in rows:
        row_label = (
            f"{label} {row['instance']} {row['solver']} {row['time_limit_seconds']}s"
        )
        if not is_true(row["fair_start_valid"]):
            failures.append(f"{row_label} fair-start witness invalid")
        if row["run_error"]:
            failures.append(f"{row_label} run_error={row['run_error']}")
        if is_true(row["watchdog_killed"]):
            failures.append(f"{row_label} watchdog killed solver")
    return failures


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def is_true(value: str) -> bool:
    return value.strip().lower() == "true"


def parse_int(value: str) -> int | None:
    if value == "":
        return None
    return int(value)


if __name__ == "__main__":
    main()
