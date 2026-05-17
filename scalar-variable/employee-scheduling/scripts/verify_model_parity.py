#!/usr/bin/env python3.14
"""Verify that employee-scheduling adapters encode the same model contract."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from _venv_bootstrap import ensure_repo_venv  # noqa: E402

ensure_repo_venv(REPO_ROOT)
sys.path[:0] = [
    str(REPO_ROOT / "src"),
    str(REPO_ROOT / "scalar-variable" / "employee-scheduling" / "src"),
]

from employee_scheduling_bench.loader import (  # noqa: E402
    enumerate_instances,
    load_instance,
    load_solution,
)
from employee_scheduling_bench.validation import validate_breakdown  # noqa: E402


@dataclass(frozen=True)
class SourceCheck:
    adapter: str
    clause: str
    path: Path
    required_fragments: tuple[str, ...]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Check employee-scheduling model parity across validator, OR-Tools, "
            "Timefold, and SolverForge."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root. Defaults to the current checkout.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    checks = _source_checks(repo_root)
    failures = _run_source_checks(checks)
    failures.extend(_check_reference_solution_costs(repo_root))

    if failures:
        print("Model parity check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise SystemExit(1)

    print("Employee-scheduling model parity checks passed.")
    print(f"Checked {len(checks)} source clauses.")


def _source_checks(repo_root: Path) -> list[SourceCheck]:
    employee_src = (
        repo_root
        / "scalar-variable"
        / "employee-scheduling"
        / "src"
        / "employee_scheduling_bench"
    )
    serializer = employee_src / "solver" / "instance_json.py"
    validator = employee_src / "validation.py"
    ortools = employee_src / "solver" / "ortools" / "main.cc"
    timefold = (
        employee_src
        / "solver"
        / "timefold"
        / "src"
        / "main"
        / "java"
        / "com"
        / "solverforgebench"
        / "nrp"
    )
    timefold_constraints = timefold / "NrpConstraintProvider.java"
    timefold_main = timefold / "Main.java"
    timefold_assignment = timefold / "domain" / "ShiftAssignment.java"
    solverforge = employee_src / "solver" / "solverforge_nrp" / "src"
    solverforge_lib = solverforge / "lib.rs"
    solverforge_domain = solverforge / "domain.rs"
    solverforge_constraints = solverforge / "constraints.rs"

    return [
        SourceCheck(
            "serializer",
            "slots are generated from every optimal coverage slot and marked minimum until the minimum count",
            serializer,
            (
                "for slot in range(day_req.optimal)",
                '"is_minimum": slot < day_req.minimum',
            ),
        ),
        SourceCheck(
            "validator",
            "shared hard constraints cover single assignment, missing skill, minimum coverage, and forbidden succession",
            validator,
            (
                "SingleAssignmentViolation",
                "MissingSkillViolation",
                "MinCoverageViolation",
                "ForbiddenSuccessionViolation",
            ),
        ),
        SourceCheck(
            "validator",
            "shared soft objective weights match INRC-II benchmark policy",
            validator,
            (
                'breakdown["optimalCoverage"] += 30',
                'breakdown["shiftOffRequests"] += 10',
                'breakdown["totalAssignmentBounds"] += 20',
                'breakdown["consecutiveWorkBounds"] += 30',
                'breakdown["consecutiveOffBounds"] += 30',
                'breakdown["consecutiveShiftTypeBounds"] += 15',
                'breakdown["workingWeekends"] += 30',
                'breakdown["completeWeekends"] += 30',
            ),
        ),
        SourceCheck(
            "ortools",
            "candidate domain excludes missing skills and initial forbidden successors",
            ortools,
            (
                "nurse.skills.find(shift.skill_idx) == nurse.skills.end()",
                "IsForbiddenSuccessor(payload, history_last_shift,",
            ),
        ),
        SourceCheck(
            "ortools",
            "minimum slots must be assigned and optional slots may be unassigned with optimal coverage penalty",
            ortools,
            (
                "if (shift.is_minimum)",
                "model.AddEquality(BoolSum(candidates), 1)",
                "model.AddLessOrEqual(BoolSum(candidates), 1)",
                "AddObjectiveTerm(&objective, unassigned, 30)",
            ),
        ),
        SourceCheck(
            "ortools",
            "hard constraints include one shift per nurse/day and adjacent forbidden succession",
            ortools,
            (
                "model.AddLessOrEqual(BoolSum(vars_by_nurse_day[nurse_idx][day]), 1)",
                "model.AddLessOrEqual(left + right, 1)",
            ),
        ),
        SourceCheck(
            "ortools",
            "soft objective weights match the shared validator",
            ortools,
            (
                "AddObjectiveTerm(&objective, var, request_count * 10)",
                "AddObjectiveTerm(&objective, under_assignments, 20)",
                "AddObjectiveTerm(&objective, over_assignments, 20)",
                "contract.max_consecutive_working, 30",
                "shift_type.max_consecutive, 15",
                "AddObjectiveTerm(&objective, incomplete, 30)",
                "AddObjectiveTerm(&objective, over_weekends, 30)",
            ),
        ),
        SourceCheck(
            "timefold",
            "entity value range is per shift, not a global all-nurses range",
            timefold_assignment,
            (
                '@PlanningVariable(valueRangeProviderRefs = "nurseRange")',
                '@ValueRangeProvider(id = "nurseRange")',
                "public List<NurseFact> getNurseRange()",
            ),
        ),
        SourceCheck(
            "timefold",
            "candidate domain excludes missing skills and initial forbidden successors",
            timefold_main,
            (
                "nurseRangeForShift(",
                "if (!nurse.getSkills().contains(skillIdx))",
                "forbiddenSuccessor(forbidden, previousShift, shiftTypeIdx)",
            ),
        ),
        SourceCheck(
            "timefold",
            "minimum slots cannot use the unassigned sentinel while optional slots can",
            timefold_main,
            (
                "if (!minimum)",
                "candidates.add(unassignedNurse)",
            ),
        ),
        SourceCheck(
            "timefold",
            "hard constraints include minimum coverage, one shift per day, required skill, and forbidden succession",
            timefold_constraints,
            (
                "minimumCoverage(factory)",
                "oneShiftPerDay(factory)",
                "requiredSkill(factory)",
                "initialForbiddenSuccession(factory)",
                "adjacentForbiddenSuccession(factory)",
            ),
        ),
        SourceCheck(
            "timefold",
            "soft objective weights match the shared validator",
            timefold_constraints,
            (
                "assignment -> 30",
                "cost += 20 *",
                "30)",
                "15)",
                "cost += 30",
            ),
        ),
        SourceCheck(
            "timefold",
            "shift-off request penalty uses the shared weight",
            timefold_assignment,
            ("return requestCount * 10",),
        ),
        SourceCheck(
            "solverforge",
            "candidate domain excludes missing skills and initial forbidden successors",
            solverforge_lib,
            (
                "nurse.skills.contains(&shift.skill_idx)",
                "problem_data.history_allows(nurse.index, shift.shift_type_idx)",
            ),
        ),
        SourceCheck(
            "solverforge",
            "minimum slots are required, nurse/day capacity is one, and adjacent forbidden succession is an assignment rule",
            solverforge_domain,
            (
                ".with_required_entity(shift_assignment_required)",
                ".with_capacity_key(shift_nurse_day_capacity_key)",
                ".with_assignment_rule(shift_assignment_rule)",
                "shift.is_minimum",
                "nurse_idx * solution.problem_data().total_days() + global_day",
                "!right.forbidden_predecessors.contains(&left.shift_type_idx)",
            ),
        ),
        SourceCheck(
            "solverforge",
            "hard constraints include minimum coverage, single assignment, required skill, and forbidden succession",
            solverforge_constraints,
            (
                '.named("minimumCoverage")',
                '.named("singleAssignmentPerDay")',
                '.named("requiredSkill")',
                '.named("initialForbiddenSuccession")',
                '.named("adjacentForbiddenSuccession")',
            ),
        ),
        SourceCheck(
            "solverforge",
            "soft objective weights match the shared validator",
            solverforge_constraints,
            (
                "HardSoftScore::of(0, 30)",
                "request_count * 10",
                "20 * (key.min_assignments",
                "20 * (total_assigned - key.max_assignments)",
                "30,",
                "15,",
                "complete_weekend_cost",
            ),
        ),
    ]


def _run_source_checks(checks: list[SourceCheck]) -> list[str]:
    failures: list[str] = []
    for check in checks:
        try:
            source = check.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            failures.append(f"{check.adapter} {check.clause}: missing {check.path}")
            continue

        missing = [
            fragment for fragment in check.required_fragments if fragment not in source
        ]
        if missing:
            rel_path = check.path.relative_to(REPO_ROOT)
            failures.append(
                f"{check.adapter} {check.clause}: {rel_path} missing {missing}"
            )
    return failures


def _check_reference_solution_costs(repo_root: Path) -> list[str]:
    data_dir = repo_root / "scalar-variable" / "employee-scheduling" / "data" / "inrc2"
    failures: list[str] = []
    checked = 0
    for info in enumerate_instances(str(data_dir)):
        if not info["solution_dir"]:
            continue
        instance = load_instance(
            info["scenario_path"],
            info["history_path"],
            info["week_paths"],
        )
        solution = load_solution(info["solution_dir"])
        validator_cost = sum(
            validate_breakdown(solution=solution, instance=instance).values()
        )
        checked += 1
        if (
            solution.cost is not None
            and solution.cost > 0
            and validator_cost != solution.cost
        ):
            failures.append(
                f"{info['name']}: reference cost mismatch, "
                f"validator={validator_cost}, reference={solution.cost}"
            )
    if checked == 0:
        failures.append("no bundled reference solutions were checked")
    return failures


if __name__ == "__main__":
    main()
