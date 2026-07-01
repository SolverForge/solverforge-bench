#!/usr/bin/env python3
"""Verify benchmark solvers start from fair, unassigned planning state."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]

SOLVER_ROOTS = [
    REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver",
    REPO_ROOT
    / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver",
    REPO_ROOT / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver",
]

SOURCE_SUFFIXES = {
    ".py",
    ".rs",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".toml",
}

SKIPPED_PARTS = {
    "target",
    "build",
    "CMakeFiles",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}

BANNED_PATTERNS = [
    "AddHint(",
    "BuildGreedyHint",
    "SolveHardSeed",
    "hard_seed",
    "greedy_hint",
    "repair_hint",
    "initial_solution",
    "initialSolution",
    "warm_start",
    "warmStart",
    "read_solution(",
    "load_solution(",
    "reference_solution",
]

PYTHON_SOLVER_WRAPPERS = [
    REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/pyvrp.py",
    REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/pyhygese.py",
    REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/solverforge.py",
    REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/solverforge_py.py",
    REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/timefold.py",
    REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/ortools/__init__.py",
    REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/vroom/__init__.py",
    REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/rustvrp/rustvrp.py",
    REPO_ROOT
    / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/solverforge.py",
    REPO_ROOT
    / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/solverforge_py.py",
    REPO_ROOT
    / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/timefold.py",
    REPO_ROOT
    / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/ortools/__init__.py",
    REPO_ROOT
    / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/solverforge.py",
    REPO_ROOT
    / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/solverforge_py.py",
    REPO_ROOT
    / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/timefold.py",
    REPO_ROOT
    / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/ortools/__init__.py",
]


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    message: str

    def format(self) -> str:
        try:
            display_path = self.path.relative_to(REPO_ROOT)
        except ValueError:
            display_path = self.path
        return f"{display_path}:{self.line}: {self.message}"


def main() -> int:
    args = parse_args()
    violations: list[Violation] = []
    violations.extend(scan_banned_patterns())
    violations.extend(check_positive_start_shapes())
    violations.extend(check_runtime_witness_wrappers())
    if args.run_id:
        violations.extend(check_postgres_rows(args.run_id, args.database_url))

    if violations:
        for violation in violations:
            print(violation.format())
        return 1

    print("fair-start verification passed")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify benchmark solvers start from fair planning state."
    )
    parser.add_argument(
        "--run-id",
        help="Optional PostgreSQL benchmark run id whose rows must all carry a valid witness.",
    )
    parser.add_argument(
        "--database-url",
        default=(
            os.environ.get("BENCH_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or "postgresql://postgres@localhost/solverforge_bench"
        ),
        help="PostgreSQL URL used with --run-id.",
    )
    return parser.parse_args()


def scan_banned_patterns() -> list[Violation]:
    violations: list[Violation] = []
    for root in SOLVER_ROOTS:
        if not root.exists():
            violations.append(Violation(root, 1, "solver root does not exist"))
            continue
        for path in sorted(root.rglob("*")):
            if not should_scan(path):
                continue
            for line_number, line in enumerate(path.read_text().splitlines(), 1):
                for pattern in BANNED_PATTERNS:
                    if pattern in line:
                        violations.append(
                            Violation(
                                path,
                                line_number,
                                f"forbidden adapter-side fair-start pattern: {pattern}",
                            )
                        )
    return violations


def should_scan(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix not in SOURCE_SUFFIXES:
        return False
    return not any(part in SKIPPED_PARTS for part in path.parts)


def check_positive_start_shapes() -> list[Violation]:
    violations: list[Violation] = []

    violations.extend(
        require_contains(
            REPO_ROOT
            / "list-variable/cvrp/src/cvrp_bench/solver/solverforge/src/lib.rs",
            "visits: Vec::new()",
            "CVRP SolverForge routes must start empty",
        )
    )
    violations.extend(
        require_contains(
            REPO_ROOT
            / "list-variable/cvrp/src/cvrp_bench/solver/timefold/src/main/java/com/cvrpbenchmark/domain/Vehicle.java",
            "this.visits = new ArrayList<>();",
            "CVRP Timefold vehicle visits must start empty",
        )
    )
    violations.extend(
        require_contains(
            REPO_ROOT
            / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/solverforge_nrp/src/lib.rs",
            "nurse_idx: None",
            "employee SolverForge shifts must start unassigned",
        )
    )
    violations.extend(
        require_contains(
            REPO_ROOT
            / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/solverforge_nrp/src/domain.rs",
            "allows_unassigned = true",
            "employee SolverForge shift variable must allow unassigned starts",
        )
    )
    violations.extend(check_employee_timefold_constructor())
    violations.extend(
        require_contains(
            REPO_ROOT
            / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/solverforge_jssp/src/lib.rs",
            "operations: Vec::new()",
            "JSSP SolverForge machine sequences must start empty",
        )
    )
    violations.extend(check_jssp_timefold_constructor())

    return violations


def check_runtime_witness_wrappers() -> list[Violation]:
    violations: list[Violation] = []
    for path in PYTHON_SOLVER_WRAPPERS:
        violations.extend(
            require_contains(
                path,
                "SolverResult",
                "solver wrapper must declare the SolverResult contract",
            )
        )
        violations.extend(
            require_contains(
                path,
                "emit_fair_start_witness(witness)",
                "solver wrapper must emit a runtime fair-start witness before solve",
            )
        )
        violations.extend(
            require_contains(
                path,
                "solver_result(",
                "solver wrapper must return SolverResult",
            )
        )

    violations.extend(
        require_contains(
            REPO_ROOT
            / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/ortools/main.cc",
            "proto.solution_hint().vars_size()",
            "employee OR-Tools must inspect CP-SAT hint fields in native witness",
        )
    )
    violations.extend(
        require_contains(
            REPO_ROOT
            / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/ortools/main.cc",
            "proto.solution_hint().vars_size()",
            "JSSP OR-Tools must inspect CP-SAT hint fields in native witness",
        )
    )
    return violations


def check_postgres_rows(run_id: str, database_url: str) -> list[Violation]:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        return [
            Violation(
                REPO_ROOT / "pyproject.toml",
                1,
                f"PostgreSQL row verification requires psycopg: {exc}",
            )
        ]

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        count(*),
                        count(*) FILTER (WHERE fair_start_valid),
                        count(*) FILTER (
                            WHERE fair_start_witness IS NOT NULL
                              AND fair_start_witness <> 'null'::jsonb
                        ),
                        array_agg(
                            row_index || ':' || solver || ':' ||
                            coalesce(fair_start_error, 'missing error')
                            ORDER BY row_index
                        ) FILTER (WHERE NOT fair_start_valid)
                    FROM benchmark_results
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                total, valid, witnessed, invalid = cur.fetchone()
    except Exception as exc:
        return [
            Violation(
                REPO_ROOT / "migrations",
                1,
                f"PostgreSQL row verification failed for run {run_id}: {exc}",
            )
        ]

    if total == 0:
        return [
            Violation(
                REPO_ROOT / "migrations",
                1,
                f"PostgreSQL run {run_id} has no benchmark rows",
            )
        ]
    if valid != total or witnessed != total:
        invalid_rows = ", ".join(invalid or [])
        return [
            Violation(
                REPO_ROOT / "migrations",
                1,
                (
                    f"PostgreSQL run {run_id} has invalid fair-start rows: "
                    f"valid={valid}/{total}, witnessed={witnessed}/{total}; "
                    f"{invalid_rows}"
                ),
            )
        ]
    return []


def require_contains(path: Path, needle: str, message: str) -> list[Violation]:
    if not path.exists():
        return [Violation(path, 1, f"{message}: file missing")]
    text = path.read_text()
    if needle not in text:
        return [Violation(path, 1, f"{message}: missing {needle!r}")]
    return []


def check_employee_timefold_constructor() -> list[Violation]:
    path = (
        REPO_ROOT
        / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/timefold/src/main/java/com/solverforgebench/nrp/domain/ShiftAssignment.java"
    )
    violations = require_contains(
        path,
        "private NurseFact nurse;",
        "employee Timefold planning variable must exist",
    )
    if violations or not path.exists():
        return violations

    text = path.read_text()
    constructor_body = extract_between(
        text,
        "public ShiftAssignment(",
        "\n    public int getId()",
    )
    if constructor_body is None:
        return [
            Violation(
                path,
                1,
                "employee Timefold constructor boundary not found for fair-start check",
            )
        ]
    nurse_assignment = constructor_assignment(constructor_body, "nurse")
    if nurse_assignment is not None:
        violations.append(
            Violation(
                path,
                line_number_for(text, nurse_assignment),
                "employee Timefold constructor must not preload nurse assignments",
            )
        )
    return violations


def check_jssp_timefold_constructor() -> list[Violation]:
    path = (
        REPO_ROOT
        / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/timefold/src/main/java/com/solverforgebench/jssp/domain/MachineSequence.java"
    )
    violations = require_contains(
        path,
        "private List<OperationAssignment> operations = new ArrayList<>();",
        "JSSP Timefold machine operations must start empty",
    )
    if violations or not path.exists():
        return violations

    text = path.read_text()
    constructor_body = extract_between(
        text,
        "public MachineSequence(int id, List<OperationAssignment> eligibleOperations)",
        "\n    public int getId()",
    )
    if constructor_body is None:
        return [
            Violation(
                path,
                1,
                "JSSP Timefold constructor boundary not found for fair-start check",
            )
        ]
    operations_assignment = constructor_assignment(constructor_body, "operations")
    if operations_assignment is not None:
        violations.append(
            Violation(
                path,
                line_number_for(text, operations_assignment),
                "JSSP Timefold constructor must not preload machine operations",
            )
        )
    return violations


def extract_between(text: str, start: str, end: str) -> str | None:
    start_idx = text.find(start)
    if start_idx < 0:
        return None
    end_idx = text.find(end, start_idx)
    if end_idx < 0:
        return None
    return text[start_idx:end_idx]


def constructor_assignment(text: str, field_name: str) -> str | None:
    for candidate in (f"this.{field_name} =", f"this.{field_name}="):
        if candidate in text:
            return candidate
    return None


def line_number_for(text: str, needle: str) -> int:
    index = text.find(needle)
    if index < 0:
        return 1
    return text.count("\n", 0, index) + 1


if __name__ == "__main__":
    sys.exit(main())
