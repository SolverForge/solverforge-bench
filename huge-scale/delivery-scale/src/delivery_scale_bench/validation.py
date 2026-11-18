"""Strict validation and scoring for delivery-at-scale fleet plans.

The ruleset is solverforge-deliveries'. Hard rules (any violation makes the
plan infeasible):

- every delivery is assigned to exactly one vehicle route;
- no more routes than vehicles;
- a route's total demand does not exceed vehicle capacity;
- every service ends by its delivery's ``max_end`` (a vehicle that arrives
  before ``min_start`` waits).

Soft cost (lower is better): total travel seconds over every non-empty route,
depot to first stop through the last stop back to the depot.
"""

from __future__ import annotations

from delivery_scale_bench.domain.models import Instance, Solution, travel_seconds


class HardConstraintViolation(ValueError):
    """Raised when a fleet plan breaks a hard rule."""


def validate_breakdown(*, solution: Solution, instance: Instance) -> dict[str, int]:
    """Return the soft-cost breakdown, raising on the first hard violation."""

    if len(solution.routes) > instance.vehicle_count:
        raise HardConstraintViolation(
            f"vehicle_count: {len(solution.routes)} routes for "
            f"{instance.vehicle_count} vehicles"
        )
    index_by_id = {delivery.id: idx for idx, delivery in enumerate(instance.deliveries)}
    seen = [False] * len(instance.deliveries)
    total_travel = 0
    for route_number, route in enumerate(solution.routes):
        if not route:
            continue
        load = 0
        clock = instance.departure_time
        x, y = instance.depot_x, instance.depot_y
        for delivery_id in route:
            index = index_by_id.get(delivery_id)
            if index is None:
                raise HardConstraintViolation(
                    f"all_deliveries_assigned: route {route_number} names unknown "
                    f"delivery {delivery_id!r}"
                )
            if seen[index]:
                raise HardConstraintViolation(
                    f"all_deliveries_assigned: {delivery_id} is visited twice"
                )
            seen[index] = True
            delivery = instance.deliveries[index]
            load += delivery.demand
            leg = travel_seconds(x, y, delivery.x, delivery.y)
            total_travel += leg
            clock = max(clock + leg, delivery.min_start) + delivery.service
            if clock > delivery.max_end:
                raise HardConstraintViolation(
                    f"delivery_time_windows: {delivery_id} service ends at {clock}, "
                    f"after {delivery.max_end}"
                )
            x, y = delivery.x, delivery.y
        if load > instance.capacity:
            raise HardConstraintViolation(
                f"vehicle_capacity: route {route_number} carries {load} > "
                f"{instance.capacity}"
            )
        total_travel += travel_seconds(x, y, instance.depot_x, instance.depot_y)

    missing = seen.count(False)
    if missing:
        raise HardConstraintViolation(
            f"all_deliveries_assigned: {missing} deliveries are unassigned"
        )
    return {"total_travel_time": total_travel}
