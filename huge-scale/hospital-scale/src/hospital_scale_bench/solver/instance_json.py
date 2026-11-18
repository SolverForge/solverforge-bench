"""The single solver-input document both native models read.

Candidate domains are computed here, once, so every solver receives exactly
the same per-skill employee domain instead of re-deriving it natively.
"""

from __future__ import annotations

import json

from hospital_scale_bench.domain.models import Instance


def skill_candidates(instance: Instance) -> list[list[int]]:
    """Employees holding each skill, in ascending employee index."""

    candidates: list[list[int]] = [[] for _ in instance.skills]
    for employee_idx, employee in enumerate(instance.employees):
        for skill in employee.skills:
            candidates[skill].append(employee_idx)
    return candidates


def serialize_instance(instance: Instance) -> str:
    document = {
        "horizon_days": instance.horizon_days,
        "hubs": [[hub.x, hub.y] for hub in instance.hubs],
        "skill_hubs": list(instance.skill_hubs),
        "skill_candidates": skill_candidates(instance),
        "employees": [
            {
                "home_hub": employee.home_hub,
                "skills": list(employee.skills),
                "unavailable_days": list(employee.unavailable_days),
                "desired_days": list(employee.desired_days),
                "undesired_days": list(employee.undesired_days),
            }
            for employee in instance.employees
        ],
        "shifts": [
            {
                "start": shift.start,
                "end": shift.end,
                "hub": shift.hub,
                "required_skill": shift.required_skill,
            }
            for shift in instance.shifts
        ],
    }
    return json.dumps(document, separators=(",", ":"))
