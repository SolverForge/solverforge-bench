"""Deterministic generator for hospital-at-scale instances.

Every instance is generated witness-first: a hidden roster that satisfies
every hard rule is drawn first, and the published shifts, availability and
preferences are derived from it. The witness proves the instance is
hard-feasible. It is stored beside the instance for validation only; no
solver ever receives it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from hospital_scale_bench.domain.models import MINUTES_PER_DAY

GENERATOR_VERSION = 1
HORIZON_DAYS = 28

# Care hubs on the uc-hospital grid; nearby search measures Manhattan distance.
HUBS: tuple[tuple[str, int, int], ...] = (
    ("Ambulatory care", 0, 0),
    ("Outpatient", 1, 0),
    ("Pediatric care", 0, 1),
    ("Neurology", 1, 1),
    ("Critical care", 2, 1),
    ("Surgery", 2, 2),
    ("Radiology", 3, 2),
)
HUB_WEIGHTS = (12, 10, 12, 16, 20, 18, 12)

# (skill name, owning hub index), the uc-hospital vocabulary.
SKILLS: tuple[tuple[str, int], ...] = (
    ("Ambulatory doctor", 0),
    ("Ambulatory nurse", 0),
    ("Outpatient doctor", 1),
    ("Outpatient nurse", 1),
    ("Pediatric doctor", 2),
    ("Pediatric nurse", 2),
    ("Neurology doctor", 3),
    ("Neurology nurse", 3),
    ("Cardiology", 3),
    ("Critical care doctor", 4),
    ("Critical care nurse", 4),
    ("Surgery doctor", 5),
    ("Surgery nurse", 5),
    ("Anaesthetics", 5),
    ("Radiology day", 6),
    ("Radiology nurse", 6),
    ("Radiology call", 6),
)

# Shift templates: (name, start minute of day, duration minutes).
TEMPLATES: tuple[tuple[str, int, int], ...] = (
    ("early", 6 * 60, 8 * 60),
    ("day", 8 * 60, 8 * 60),
    ("late", 14 * 60, 8 * 60),
    ("long", 7 * 60, 12 * 60),
    ("night", 22 * 60, 8 * 60),
)
NIGHT = 4
DAYTIME_TEMPLATES = (0, 1, 2)
HUB_TEMPLATES: tuple[tuple[int, ...], ...] = (
    DAYTIME_TEMPLATES,  # Ambulatory care
    DAYTIME_TEMPLATES,  # Outpatient
    (0, 1, 2, 3, 4),
    (0, 1, 2, 3, 4),
    (0, 1, 2, 3, 4),
    (0, 1, 2, 3, 4),
    (0, 1, 2, 3),  # Radiology
)
DAY_TEMPLATE_CAP = 20
# Nights touch two calendar days, so the one-shift-per-day rule forbids
# consecutive nights; alternate nights over the horizon allow at most 14.
NIGHT_TEMPLATE_CAP = 12


@dataclass(frozen=True)
class Tier:
    name: str
    employees: int
    shifts: int
    seed: int


TIERS: tuple[Tier, ...] = (
    Tier("hs-e1000-s10000", 1_000, 10_000, 1_001),
    Tier("hs-e10000-s100000", 10_000, 100_000, 10_001),
)
GROUPS: dict[str, list[str]] = {
    "quick": ["hs-e1000-s10000"],
    "canonical": ["hs-e10000-s100000"],
}


def generate(tier: Tier) -> tuple[dict, dict]:
    """Return the published instance document and its hidden witness."""

    rng = random.Random(tier.seed)
    skills_by_hub: list[list[int]] = [[] for _ in HUBS]
    for skill_idx, (_, hub) in enumerate(SKILLS):
        skills_by_hub[hub].append(skill_idx)

    homes = rng.choices(range(len(HUBS)), weights=HUB_WEIGHTS, k=tier.employees)
    employee_skills: list[list[int]] = []
    employee_templates: list[int] = []
    for home in homes:
        own = skills_by_hub[home]
        primary = rng.choice(own)
        skills = [primary]
        if len(own) > 1 and rng.random() < 0.30:
            skills.append(rng.choice([skill for skill in own if skill != primary]))
        if rng.random() < 0.15:
            neighbour = rng.choice(_adjacent_hubs(home))
            extra = rng.choice(skills_by_hub[neighbour])
            if extra not in skills:
                skills.append(extra)
        employee_skills.append(skills)
        employee_templates.append(rng.choice(HUB_TEMPLATES[home]))

    loads = _loads(rng, tier, employee_templates)

    witness_shifts: list[tuple[int, int, int, int, int]] = []
    employees: list[dict] = []
    for employee_idx, home in enumerate(homes):
        template = employee_templates[employee_idx]
        _, start_minute, duration = TEMPLATES[template]
        work_days = _work_days(rng, loads[employee_idx], template)
        skills = employee_skills[employee_idx]
        eligible = [
            skill for skill in skills if template in HUB_TEMPLATES[SKILLS[skill][1]]
        ]
        touched: set[int] = set()
        for day in work_days:
            if skills[0] in eligible and rng.random() < 0.70:
                skill = skills[0]
            else:
                skill = rng.choice(eligible)
            start = day * MINUTES_PER_DAY + start_minute
            end = start + duration
            touched.update(
                range(start // MINUTES_PER_DAY, (end - 1) // MINUTES_PER_DAY + 1)
            )
            witness_shifts.append((start, end, SKILLS[skill][1], skill, employee_idx))

        free_days = [day for day in range(HORIZON_DAYS) if day not in touched]
        unavailable = sorted(
            rng.sample(free_days, min(len(free_days), rng.randint(1, 4)))
        )
        open_days = [day for day in range(HORIZON_DAYS) if day not in unavailable]
        worked = sorted(touched.intersection(open_days))
        desired = _preference_days(rng, worked, open_days, 0.50, set())
        undesired = _preference_days(rng, worked, open_days, 0.60, set(desired))
        employees.append(
            {
                "id": f"E{employee_idx:05d}",
                "home_hub": home,
                "skills": sorted(skills),
                "unavailable_days": unavailable,
                "desired_days": desired,
                "undesired_days": undesired,
            }
        )

    # Shuffle before the stable sort so ties never carry witness order.
    rng.shuffle(witness_shifts)
    witness_shifts.sort(key=lambda shift: (shift[0], shift[2], shift[3]))
    shifts = [
        {
            "id": f"S{shift_idx:06d}",
            "start": start,
            "end": end,
            "hub": hub,
            "required_skill": skill,
        }
        for shift_idx, (start, end, hub, skill, _) in enumerate(witness_shifts)
    ]
    instance = {
        "name": tier.name,
        "generator_version": GENERATOR_VERSION,
        "seed": tier.seed,
        "horizon_days": HORIZON_DAYS,
        "hubs": [{"name": name, "x": x, "y": y} for name, x, y in HUBS],
        "skills": [name for name, _ in SKILLS],
        "skill_hubs": [hub for _, hub in SKILLS],
        "employees": employees,
        "shifts": shifts,
    }
    witness = {
        "name": tier.name,
        "assignments": [employees[shift[4]]["id"] for shift in witness_shifts],
    }
    return instance, witness


def _adjacent_hubs(hub: int) -> list[int]:
    _, x, y = HUBS[hub]
    return [
        other
        for other, (_, ox, oy) in enumerate(HUBS)
        if abs(ox - x) + abs(oy - y) == 1
    ]


def _cap(template: int) -> int:
    return NIGHT_TEMPLATE_CAP if template == NIGHT else DAY_TEMPLATE_CAP


def _loads(rng: random.Random, tier: Tier, templates: list[int]) -> list[int]:
    base, remainder = divmod(tier.shifts, tier.employees)
    loads = [base + (1 if index < remainder else 0) for index in range(tier.employees)]
    rng.shuffle(loads)
    for index, template in enumerate(templates):
        if loads[index] > _cap(template):
            raise ValueError(f"{tier.name}: base load exceeds template capacity")
    # Spread the load: move up to three shifts between random employee pairs
    # while every employee keeps at least one shift and stays under capacity.
    for _ in range(tier.employees * 2):
        giver = rng.randrange(tier.employees)
        taker = rng.randrange(tier.employees)
        amount = rng.randint(1, 3)
        if giver == taker:
            continue
        if loads[giver] - amount < 1:
            continue
        if loads[taker] + amount > _cap(templates[taker]):
            continue
        loads[giver] -= amount
        loads[taker] += amount
    return loads


def _work_days(rng: random.Random, load: int, template: int) -> list[int]:
    if template != NIGHT:
        return sorted(rng.sample(range(HORIZON_DAYS), load))
    # Nights never run on the last day, so they stay inside the horizon.
    candidates = list(range(HORIZON_DAYS - 1))
    while True:
        rng.shuffle(candidates)
        chosen: set[int] = set()
        for day in candidates:
            if day - 1 in chosen or day + 1 in chosen:
                continue
            chosen.add(day)
            if len(chosen) == load:
                return sorted(chosen)


def _preference_days(
    rng: random.Random,
    worked: list[int],
    open_days: list[int],
    worked_share: float,
    taken: set[int],
) -> list[int]:
    days: set[int] = set()
    for _ in range(rng.randint(0, 3)):
        pool = worked if worked and rng.random() < worked_share else open_days
        day = rng.choice(pool)
        if day not in taken:
            days.add(day)
    return sorted(days)
