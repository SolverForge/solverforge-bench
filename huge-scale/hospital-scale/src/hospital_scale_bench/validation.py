"""Strict validation and scoring for hospital-at-scale rosters.

Hard rules (any violation makes the roster infeasible):

- every shift is assigned to an existing employee;
- the employee has the shift's required skill;
- an employee's shifts do not overlap;
- an employee has at least 10 hours between two shifts;
- an employee works at most one shift per calendar day touched;
- an employee is never assigned a shift touching an unavailable day.

Soft cost (lower is better), identical in every solver model:

- ``undesired_day``: +10 per (shift, undesired day it touches);
- ``desired_day``: -10 per (shift, desired day it touches);
- ``balance_assignments``: + sum over employees of (assigned shift count)^2.
"""

from __future__ import annotations

from collections import defaultdict

from hospital_scale_bench.domain.models import Instance, Solution

MINIMUM_REST_MINUTES = 600
PREFERENCE_WEIGHT = 10


class HardConstraintViolation(ValueError):
    """Raised when a roster breaks a hard rule."""


def validate_breakdown(*, solution: Solution, instance: Instance) -> dict[str, int]:
    """Return the soft-cost breakdown, raising on the first hard violation."""

    assignment = _employee_indices(solution, instance)
    shifts_by_employee: dict[int, list[int]] = defaultdict(list)
    for shift_idx, employee_idx in enumerate(assignment):
        shifts_by_employee[employee_idx].append(shift_idx)

    shifts = instance.shifts
    for employee_idx, shift_indices in shifts_by_employee.items():
        employee = instance.employees[employee_idx]
        skills = set(employee.skills)
        unavailable = set(employee.unavailable_days)
        touched_days: set[int] = set()
        ordered = sorted(shift_indices, key=lambda idx: (shifts[idx].start, idx))
        previous = None
        for shift_idx in ordered:
            shift = shifts[shift_idx]
            if shift.required_skill not in skills:
                raise HardConstraintViolation(
                    f"required_skill: {employee.id} lacks "
                    f"{instance.skills[shift.required_skill]!r} for {shift.id}"
                )
            days = range(shift.first_day, shift.last_day + 1)
            for day in days:
                if day in unavailable:
                    raise HardConstraintViolation(
                        f"unavailable_employee: {employee.id} is unavailable on "
                        f"day {day} touched by {shift.id}"
                    )
                if day in touched_days:
                    raise HardConstraintViolation(
                        f"one_shift_per_day: {employee.id} works more than one "
                        f"shift touching day {day} ({shift.id})"
                    )
            touched_days.update(days)
            if previous is not None:
                if shift.start < previous.end:
                    raise HardConstraintViolation(
                        f"overlapping_shift: {employee.id} works {previous.id} "
                        f"and {shift.id} at the same time"
                    )
                gap = shift.start - previous.end
                if gap < MINIMUM_REST_MINUTES:
                    raise HardConstraintViolation(
                        f"minimum_rest: {employee.id} rests {gap} minutes between "
                        f"{previous.id} and {shift.id}"
                    )
            # Sorted by start and non-overlapping, so the previous shift also
            # carries the latest end seen so far.
            previous = shift

    return soft_breakdown(instance, assignment)


def soft_breakdown(instance: Instance, assignment: list[int]) -> dict[str, int]:
    undesired_hits = 0
    desired_hits = 0
    counts: dict[int, int] = defaultdict(int)
    for shift_idx, employee_idx in enumerate(assignment):
        shift = instance.shifts[shift_idx]
        employee = instance.employees[employee_idx]
        counts[employee_idx] += 1
        for day in range(shift.first_day, shift.last_day + 1):
            if day in employee.undesired_days:
                undesired_hits += 1
            if day in employee.desired_days:
                desired_hits += 1
    return {
        "undesired_day": PREFERENCE_WEIGHT * undesired_hits,
        "desired_day": -PREFERENCE_WEIGHT * desired_hits,
        "balance_assignments": sum(count * count for count in counts.values()),
    }


def _employee_indices(solution: Solution, instance: Instance) -> list[int]:
    if len(solution.assignments) != len(instance.shifts):
        raise HardConstraintViolation(
            f"assigned_shift: solution covers {len(solution.assignments)} shifts, "
            f"instance has {len(instance.shifts)}"
        )
    index_by_id = {employee.id: idx for idx, employee in enumerate(instance.employees)}
    indices: list[int] = []
    for shift, employee_id in zip(instance.shifts, solution.assignments, strict=True):
        if employee_id is None:
            raise HardConstraintViolation(f"assigned_shift: {shift.id} is unassigned")
        employee_idx = index_by_id.get(employee_id)
        if employee_idx is None:
            raise HardConstraintViolation(
                f"assigned_shift: {shift.id} names unknown employee {employee_id!r}"
            )
        indices.append(employee_idx)
    return indices
