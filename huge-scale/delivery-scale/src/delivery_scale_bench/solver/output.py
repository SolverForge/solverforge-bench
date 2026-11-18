"""Shared output handling for the delivery-at-scale solver wrappers."""

from __future__ import annotations

from collections import Counter

from delivery_scale_bench.domain.models import Instance, Solution
from solverforge_bench.model import NoSolutionFoundError


def solution_from_native(
    instance: Instance,
    output: dict,
    *,
    solver_label: str,
    solver_metadata: dict | None = None,
) -> Solution:
    """Translate native delivery indices, rejecting an inexact assignment.

    Every delivery is required. A plan that misses or repeats a delivery is a
    failed solver invocation, not a solution to send to the validator.
    """

    routes = output["routes"]
    counts = Counter(index for route in routes for index in route)
    total = len(instance.deliveries)
    out_of_range = [index for index in counts if not 0 <= index < total]
    if out_of_range:
        raise ValueError(
            f"{solver_label} returned unknown delivery indices {out_of_range[:5]}"
        )
    duplicated = sum(1 for count in counts.values() if count > 1)
    if duplicated:
        raise ValueError(
            f"{solver_label} visited {duplicated} deliveries more than once"
        )
    unassigned = total - len(counts)
    if unassigned:
        raise NoSolutionFoundError(
            f"{solver_label} ended with {unassigned} of {total} deliveries unassigned",
            native_fields={
                "unassigned_deliveries": unassigned,
                "native_reported_score": output.get("reported_score"),
            },
        )
    deliveries = instance.deliveries
    reported_cost = output.get("reported_cost")
    fresh_cost = output.get("fresh_cost")
    return Solution(
        routes=[[deliveries[index].id for index in route] for route in routes],
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
