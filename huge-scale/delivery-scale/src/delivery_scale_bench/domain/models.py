"""Delivery-at-scale instance and returned-solution models.

Coordinates are integer metres on a flat city plane. Times are seconds after
midnight. Travel time between two points is the shared integer rule in
``travel_seconds``, which both solver models implement identically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel

#: Vehicle speed in metres per second (36 km/h city driving).
SPEED_MPS = 10.0


def travel_seconds(ax: int, ay: int, bx: int, by: int) -> int:
    """Euclidean distance over SPEED_MPS, rounded half up to whole seconds."""

    dx = ax - bx
    dy = ay - by
    return int(math.floor(math.sqrt(float(dx * dx + dy * dy)) / SPEED_MPS + 0.5))


@dataclass(frozen=True)
class Delivery:
    id: str
    x: int
    y: int
    demand: int
    min_start: int
    max_end: int
    service: int


@dataclass(frozen=True)
class Instance:
    name: str
    depot_x: int
    depot_y: int
    departure_time: int
    vehicle_count: int
    capacity: int
    deliveries: tuple[Delivery, ...]


class Solution(BaseModel):
    """Delivery ids in visiting order, one list per vehicle (empty lists allowed)."""

    routes: list[list[str]]
    cost: int | None = None
    reported_cost: int | None = None
    fresh_cost: int | None = None
    score_delta: int | None = None
    score_drift: bool | None = None
    reported_score: str | None = None
    fresh_score: str | None = None
    solver_metadata: dict | None = None
    validator_cost: int | None = None
    validator_breakdown: dict[str, int] | None = None
    validator_model_delta: int | None = None
    solution_artifact: str | None = None
