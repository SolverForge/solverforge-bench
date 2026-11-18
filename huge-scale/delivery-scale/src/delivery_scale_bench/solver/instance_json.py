"""The single solver-input document both native models read.

Coordinates travel as integers; each model derives travel time with the same
integer rule as ``domain.models.travel_seconds``.
"""

from __future__ import annotations

import json

from delivery_scale_bench.domain.models import SPEED_MPS, Instance


def serialize_instance(instance: Instance) -> str:
    deliveries = instance.deliveries
    document = {
        "speed_mps": SPEED_MPS,
        "depot": [instance.depot_x, instance.depot_y],
        "departure_time": instance.departure_time,
        "vehicle_count": instance.vehicle_count,
        "capacity": instance.capacity,
        "xs": [delivery.x for delivery in deliveries],
        "ys": [delivery.y for delivery in deliveries],
        "demands": [delivery.demand for delivery in deliveries],
        "min_starts": [delivery.min_start for delivery in deliveries],
        "max_ends": [delivery.max_end for delivery in deliveries],
        "services": [delivery.service for delivery in deliveries],
    }
    return json.dumps(document, separators=(",", ":"))
