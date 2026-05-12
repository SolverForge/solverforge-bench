#!/usr/bin/env python3
"""Verify that employee-scheduling adapters encode the same model contract."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
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
            "Timefold Java, and SolverForge."
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
    ortools = employee_src / "solver" / "ortools.py"
    timefold = (
        employee_src
        / "solver"
        / "timefold_java"
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
                'if shift["skill_idx"] not in nurse["skills"]',
                'and shift["shift_type_idx"] in forbidden_successors[history_last_shift]',
            ),
        ),
        SourceCheck(
            "ortools",
            "minimum slots must be assigned and optional slots may be unassigned with optimal coverage penalty",
            ortools,
            (
                'if shift["is_minimum"]:',
                "model.Add(sum(candidates) == 1)",
                "model.Add(sum(candidates) <= 1)",
                "objective_terms.append(30 * unassigned)",
            ),
        ),
        SourceCheck(
            "ortools",
            "hard constraints include one shift per nurse/day and adjacent forbidden succession",
            ortools,
            (
                "model.Add(sum(vars_by_nurse_day[(nurse_idx, day)]) <= 1)",
                "model.Add(left + right <= 1)",
            ),
        ),
        SourceCheck(
            "ortools",
            "soft objective weights match the shared validator",
            ortools,
            (
                "objective_terms.append(request_count * 10 * var)",
                "objective_terms.append(20 * under_assignments)",
                "objective_terms.append(20 * over_assignments)",
                "weight=30",
                "weight=15",
                "objective_terms.append(30 * incomplete)",
                "objective_terms.append(30 * over_weekends)",
            ),
        ),
        SourceCheck(
            "timefold_java",
            "entity value range is per shift, not a global all-nurses range",
            timefold_assignment,
            (
                '@PlanningVariable(valueRangeProviderRefs = "nurseRange")',
                '@ValueRangeProvider(id = "nurseRange")',
                "public List<NurseFact> getNurseRange()",
            ),
        ),
        SourceCheck(
            "timefold_java",
            "candidate domain excludes missing skills and initial forbidden successors",
            timefold_main,
            (
                "nurseRangeForShift(",
                "if (!nurse.getSkills().contains(skillIdx))",
                "forbiddenSuccessor(forbidden, previousShift, shiftTypeIdx)",
            ),
        ),
        SourceCheck(
            "timefold_java",
            "minimum slots cannot use the unassigned sentinel while optional slots can",
            timefold_main,
            (
                "if (!minimum)",
                "candidates.add(unassignedNurse)",
            ),
        ),
        SourceCheck(
            "timefold_java",
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
            "timefold_java",
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
            "timefold_java",
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
        if solution.cost > 0 and validator_cost != solution.cost:
            failures.append(
                f"{info['name']}: reference cost mismatch, "
                f"validator={validator_cost}, reference={solution.cost}"
            )
    if checked == 0:
        failures.append("no bundled reference solutions were checked")
    return failures


if __name__ == "__main__":
    main()
