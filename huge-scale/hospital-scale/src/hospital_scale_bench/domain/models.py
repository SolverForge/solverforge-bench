"""Hospital-at-scale instance and returned-solution models.

Time is measured in minutes from the start of the planning horizon (day 0,
00:00). A shift touches calendar day ``d`` when at least one of its minutes
falls inside ``[d * 1440, (d + 1) * 1440)``.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

MINUTES_PER_DAY = 1440


@dataclass(frozen=True)
class Hub:
    name: str
    x: int
    y: int


@dataclass(frozen=True)
class Employee:
    id: str
    home_hub: int
    skills: tuple[int, ...]
    unavailable_days: tuple[int, ...]
    desired_days: tuple[int, ...]
    undesired_days: tuple[int, ...]


@dataclass(frozen=True)
class Shift:
    id: str
    start: int
    end: int
    hub: int
    required_skill: int

    @property
    def first_day(self) -> int:
        return self.start // MINUTES_PER_DAY

    @property
    def last_day(self) -> int:
        return (self.end - 1) // MINUTES_PER_DAY


@dataclass(frozen=True)
class Instance:
    name: str
    horizon_days: int
    hubs: tuple[Hub, ...]
    skills: tuple[str, ...]
    skill_hubs: tuple[int, ...]
    employees: tuple[Employee, ...]
    shifts: tuple[Shift, ...]


class Solution(BaseModel):
    """Employee id per shift, in instance shift order."""

    assignments: list[str | None]
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
