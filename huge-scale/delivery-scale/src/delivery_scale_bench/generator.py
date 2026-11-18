"""Deterministic generator for delivery-at-scale instances.

Witness-first, like hospital-scale: deliveries are drawn, a hidden fleet plan
that meets every hard rule is built from them (sweep around the depot, cut by
capacity and day length, nearest-neighbour order inside each route), and every
time window is placed around the witness service time. The witness proves the
instance is feasible; no solver receives it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from delivery_scale_bench.domain.models import travel_seconds

GENERATOR_VERSION = 1
CITY_METRES = 30_000
DEPOT = (CITY_METRES // 2, CITY_METRES // 2)
DEPARTURE = 6 * 3600
DAY_END = 22 * 3600
CAPACITY = 200
MAX_ROUTE_STOPS = 45
SPARE_VEHICLE_SHARE = 0.05
NEIGHBOURHOODS = 60
QUARTER_HOUR = 900


@dataclass(frozen=True)
class Tier:
    name: str
    deliveries: int
    seed: int


TIERS: tuple[Tier, ...] = (
    Tier("ds-s2000", 2_000, 2_001),
    Tier("ds-s10000", 10_000, 10_001),
)
GROUPS: dict[str, list[str]] = {
    "quick": ["ds-s2000"],
    "canonical": ["ds-s10000"],
}


def generate(tier: Tier) -> tuple[dict, dict]:
    """Return the published instance document and its hidden witness."""

    rng = random.Random(tier.seed)
    points = _points(rng, tier.deliveries)
    demands = [rng.choice((1, 1, 2, 2, 3, 4, 5, 6, 8, 10)) for _ in points]
    services = [60 * rng.randint(3, 15) for _ in points]

    routes = _witness_routes(points, demands, services)
    min_starts = [0] * len(points)
    max_ends = [0] * len(points)
    for route in routes:
        for index, start in zip(
            route, _service_starts(route, points, services), strict=True
        ):
            min_starts[index], max_ends[index] = _window(rng, start, services[index])

    vehicle_count = len(routes) + math.ceil(len(routes) * SPARE_VEHICLE_SHARE)
    ids = [f"D{index:06d}" for index in range(len(points))]
    instance = {
        "name": tier.name,
        "generator_version": GENERATOR_VERSION,
        "seed": tier.seed,
        "depot": {"x": DEPOT[0], "y": DEPOT[1]},
        "departure_time": DEPARTURE,
        "vehicle_count": vehicle_count,
        "capacity": CAPACITY,
        "deliveries": [
            {
                "id": ids[index],
                "x": x,
                "y": y,
                "demand": demands[index],
                "min_start": min_starts[index],
                "max_end": max_ends[index],
                "service": services[index],
            }
            for index, (x, y) in enumerate(points)
        ],
    }
    witness = {
        "name": tier.name,
        "routes": [[ids[index] for index in route] for route in routes],
    }
    return instance, witness


def _points(rng: random.Random, count: int) -> list[tuple[int, int]]:
    centres = [
        (
            rng.randint(2_000, CITY_METRES - 2_000),
            rng.randint(2_000, CITY_METRES - 2_000),
        )
        for _ in range(NEIGHBOURHOODS)
    ]
    points = []
    for _ in range(count):
        if rng.random() < 0.2:
            point = (rng.randint(0, CITY_METRES), rng.randint(0, CITY_METRES))
        else:
            cx, cy = rng.choice(centres)
            point = (
                min(CITY_METRES, max(0, round(rng.gauss(cx, 1_500)))),
                min(CITY_METRES, max(0, round(rng.gauss(cy, 1_500)))),
            )
        points.append(point)
    return points


def _witness_routes(
    points: list[tuple[int, int]], demands: list[int], services: list[int]
) -> list[list[int]]:
    """Sweep around the depot, cut by capacity, stop count and day length."""

    order = sorted(
        range(len(points)),
        key=lambda index: (
            math.atan2(points[index][1] - DEPOT[1], points[index][0] - DEPOT[0]),
            index,
        ),
    )
    routes: list[list[int]] = []
    chunk: list[int] = []
    load = 0
    for index in order:
        candidate = chunk + [index]
        if chunk and (
            load + demands[index] > CAPACITY
            or len(candidate) > MAX_ROUTE_STOPS
            or _route_end(_nearest_neighbour(candidate, points), points, services)
            > DAY_END
        ):
            routes.append(_nearest_neighbour(chunk, points))
            chunk, load = [], 0
            candidate = [index]
        chunk = candidate
        load += demands[index]
    if chunk:
        routes.append(_nearest_neighbour(chunk, points))
    return routes


def _nearest_neighbour(chunk: list[int], points: list[tuple[int, int]]) -> list[int]:
    remaining = set(chunk)
    route = []
    x, y = DEPOT
    while remaining:
        nxt = min(
            remaining, key=lambda index: (travel_seconds(x, y, *points[index]), index)
        )
        remaining.remove(nxt)
        route.append(nxt)
        x, y = points[nxt]
    return route


def _service_starts(
    route: list[int], points: list[tuple[int, int]], services: list[int]
) -> list[int]:
    starts = []
    clock = DEPARTURE
    x, y = DEPOT
    for index in route:
        clock += travel_seconds(x, y, *points[index])
        starts.append(clock)
        clock += services[index]
        x, y = points[index]
    return starts


def _route_end(
    route: list[int], points: list[tuple[int, int]], services: list[int]
) -> int:
    starts = _service_starts(route, points, services)
    return starts[-1] + services[route[-1]]


def _window(rng: random.Random, start: int, service: int) -> tuple[int, int]:
    """A window containing the witness service, so the witness never waits."""

    end = start + service
    if rng.random() < 0.25:
        return DEPARTURE, DAY_END
    width = rng.choice((3600, 2 * 3600, 3 * 3600, 4 * 3600))
    lead = rng.randint(0, max(0, width - service))
    min_start = max(DEPARTURE, (start - lead) // QUARTER_HOUR * QUARTER_HOUR)
    max_end = min_start + width
    if max_end < end:
        max_end = -(-end // QUARTER_HOUR) * QUARTER_HOUR
    return min_start, max(max_end, end)
