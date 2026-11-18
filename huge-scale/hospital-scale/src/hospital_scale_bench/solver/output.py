"""Shared output handling for the hospital-at-scale solver wrappers."""

from __future__ import annotations

from hospital_scale_bench.domain.models import Instance, Solution
from solverforge_bench.model import NoSolutionFoundError


def solution_from_native(
    instance: Instance,
    output: dict,
    *,
    solver_label: str,
    solver_metadata: dict | None = None,
) -> Solution:
    """Translate native employee indices, rejecting any unassigned shift.

    Every shift is required, so a roster with an unassigned shift is a failed
    solver invocation, not a solution to send to the validator.
    """

    indices = output["assignments"]
    if len(indices) != len(instance.shifts):
        raise ValueError(
            f"{solver_label} returned {len(indices)} assignments for "
            f"{len(instance.shifts)} shifts"
        )
    unassigned = sum(index is None for index in indices)
    if unassigned:
        raise NoSolutionFoundError(
            f"{solver_label} ended with {unassigned} of {len(indices)} shifts unassigned",
            native_fields={
                "unassigned_shifts": unassigned,
                "native_hard_violations": output.get("hard_violations"),
                "native_reported_score": output.get("reported_score"),
            },
        )
    employees = instance.employees
    reported_cost = output.get("reported_cost")
    fresh_cost = output.get("fresh_cost")
    return Solution(
        assignments=[employees[index].id for index in indices],
        cost=fresh_cost,
        reported_cost=reported_cost,
        fresh_cost=fresh_cost,
        score_delta=(
            fresh_cost - reported_cost
            if fresh_cost is not None and reported_cost is not None
            else None
        ),
        score_drift=output.get("reported_score") != output.get("fresh_score"),
        reported_score=output.get("reported_score"),
        fresh_score=output.get("fresh_score"),
        solver_metadata=solver_metadata,
    )
