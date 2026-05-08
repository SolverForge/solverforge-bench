from employee_scheduling_bench.domain.models import Instance, Solution

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class HardConstraintViolation(Exception):
    pass


class SingleAssignmentViolation(HardConstraintViolation):
    pass


class MinCoverageViolation(HardConstraintViolation):
    pass


class ForbiddenSuccessionViolation(HardConstraintViolation):
    pass


class MissingSkillViolation(HardConstraintViolation):
    pass


def validate(solution: Solution, instance: Instance) -> int:
    """Validate a solution against an INRC-II instance.

    Raises HardConstraintViolation subclasses for infeasible solutions.
    Returns the total soft constraint cost for feasible solutions.
    """
    scenario = instance.scenario
    nurse_by_id = {n.id: n for n in scenario.nurses}
    contract_by_id = {c.id: c for c in scenario.contracts}
    forbidden = {
        f.precedingShiftType: set(f.succeedingShiftTypes)
        for f in scenario.forbiddenShiftTypeSuccessions
    }

    num_weeks = len(solution.assignments)
    total_days = num_weeks * 7

    # Build per-nurse schedule: list of (shift_type, skill) or None for each day
    nurse_schedule: dict[str, list[tuple[str, str] | None]] = {
        n.id: [None] * total_days for n in scenario.nurses
    }

    for week_idx, week_assignments in enumerate(solution.assignments):
        for a in week_assignments:
            day_offset = DAYS.index(a.day)
            global_day = week_idx * 7 + day_offset

            # Hard: single assignment per day
            if nurse_schedule[a.nurse][global_day] is not None:
                raise SingleAssignmentViolation(
                    f"Nurse {a.nurse} has multiple assignments on week {week_idx} {a.day}"
                )
            nurse_schedule[a.nurse][global_day] = (a.shiftType, a.skill)

            # Hard: missing skill
            nurse = nurse_by_id[a.nurse]
            if a.skill not in nurse.skills:
                raise MissingSkillViolation(
                    f"Nurse {a.nurse} lacks skill {a.skill} for assignment on {a.day}"
                )

    # Hard: minimum coverage
    for week_idx, week_data in enumerate(instance.weeks):
        # Count assignments per (shift, skill, day)
        coverage: dict[tuple[str, str, str], int] = {}
        for a in solution.assignments[week_idx]:
            key = (a.shiftType, a.skill, a.day)
            coverage[key] = coverage.get(key, 0) + 1

        for req in week_data.requirements:
            for day_name, day_req in [
                ("Mon", req.requirementOnMonday),
                ("Tue", req.requirementOnTuesday),
                ("Wed", req.requirementOnWednesday),
                ("Thu", req.requirementOnThursday),
                ("Fri", req.requirementOnFriday),
                ("Sat", req.requirementOnSaturday),
                ("Sun", req.requirementOnSunday),
            ]:
                actual = coverage.get((req.shiftType, req.skill, day_name), 0)
                if actual < day_req.minimum:
                    raise MinCoverageViolation(
                        f"Week {week_idx} {day_name}: {req.shiftType}/{req.skill} "
                        f"has {actual} nurses, minimum is {day_req.minimum}"
                    )

    # Hard: forbidden shift successions (across all days including cross-week)
    for nurse_id, schedule in nurse_schedule.items():
        last_shift = instance.history.nurseHistory[
            next(
                i
                for i, nh in enumerate(instance.history.nurseHistory)
                if nh.nurse == nurse_id
            )
        ].lastAssignedShiftType

        for day in range(total_days):
            if schedule[day] is not None:
                current_shift = schedule[day][0]
                prev_shift = (
                    last_shift
                    if day == 0
                    else (
                        schedule[day - 1][0] if schedule[day - 1] is not None else None
                    )
                )
                if (
                    prev_shift
                    and prev_shift in forbidden
                    and current_shift in forbidden[prev_shift]
                ):
                    week = day // 7
                    day_name = DAYS[day % 7]
                    raise ForbiddenSuccessionViolation(
                        f"Nurse {nurse_id}: forbidden succession {prev_shift} -> {current_shift} "
                        f"on week {week} {day_name}"
                    )

    # Soft constraints
    cost = 0

    # Soft: optimal coverage (under-staffing below optimal)
    for week_idx, week_data in enumerate(instance.weeks):
        coverage: dict[tuple[str, str, str], int] = {}
        for a in solution.assignments[week_idx]:
            key = (a.shiftType, a.skill, a.day)
            coverage[key] = coverage.get(key, 0) + 1

        for req in week_data.requirements:
            for day_name, day_req in [
                ("Mon", req.requirementOnMonday),
                ("Tue", req.requirementOnTuesday),
                ("Wed", req.requirementOnWednesday),
                ("Thu", req.requirementOnThursday),
                ("Fri", req.requirementOnFriday),
                ("Sat", req.requirementOnSaturday),
                ("Sun", req.requirementOnSunday),
            ]:
                actual = coverage.get((req.shiftType, req.skill, day_name), 0)
                if actual < day_req.optimal:
                    cost += 30 * (day_req.optimal - actual)

    # Soft: shift-off request violations
    for week_idx, week_data in enumerate(instance.weeks):
        for req in week_data.shiftOffRequests:
            day_offset = DAYS.index(req.day)
            global_day = week_idx * 7 + day_offset
            entry = nurse_schedule[req.nurse][global_day]
            if entry is not None:
                if req.shiftType == "Any" or entry[0] == req.shiftType:
                    cost += 10

    # Per-nurse soft constraints
    for nurse_id, schedule in nurse_schedule.items():
        nurse = nurse_by_id[nurse_id]
        contract = contract_by_id[nurse.contract]
        nurse_hist = next(
            nh for nh in instance.history.nurseHistory if nh.nurse == nurse_id
        )

        # Total assignments
        total_assigned = sum(1 for s in schedule if s is not None)
        total_assigned += nurse_hist.numberOfAssignments
        if total_assigned < contract.minimumNumberOfAssignments:
            cost += 20 * (contract.minimumNumberOfAssignments - total_assigned)
        elif total_assigned > contract.maximumNumberOfAssignments:
            cost += 20 * (total_assigned - contract.maximumNumberOfAssignments)

        # Consecutive working days violations
        cons_work = (
            nurse_hist.numberOfConsecutiveWorkingDays
            if nurse_hist.lastAssignedShiftType != "None"
            else 0
        )
        for day in range(total_days):
            if schedule[day] is not None:
                cons_work += 1
            else:
                if cons_work > 0:
                    if cons_work < contract.minimumNumberOfConsecutiveWorkingDays:
                        cost += 30 * (
                            contract.minimumNumberOfConsecutiveWorkingDays - cons_work
                        )
                    if cons_work > contract.maximumNumberOfConsecutiveWorkingDays:
                        cost += 30 * (
                            cons_work - contract.maximumNumberOfConsecutiveWorkingDays
                        )
                cons_work = 0
        # End-of-horizon streak
        if cons_work > contract.maximumNumberOfConsecutiveWorkingDays:
            cost += 30 * (cons_work - contract.maximumNumberOfConsecutiveWorkingDays)

        # Consecutive days off violations
        cons_off = (
            nurse_hist.numberOfConsecutiveDaysOff
            if nurse_hist.lastAssignedShiftType == "None"
            else 0
        )
        for day in range(total_days):
            if schedule[day] is None:
                cons_off += 1
            else:
                if cons_off > 0:
                    if cons_off < contract.minimumNumberOfConsecutiveDaysOff:
                        cost += 30 * (
                            contract.minimumNumberOfConsecutiveDaysOff - cons_off
                        )
                    if cons_off > contract.maximumNumberOfConsecutiveDaysOff:
                        cost += 30 * (
                            cons_off - contract.maximumNumberOfConsecutiveDaysOff
                        )
                cons_off = 0
        if cons_off > contract.maximumNumberOfConsecutiveDaysOff:
            cost += 30 * (cons_off - contract.maximumNumberOfConsecutiveDaysOff)

        # Consecutive shift type assignments
        for st in scenario.shiftTypes:
            cons_shift = 0
            if nurse_hist.lastAssignedShiftType == st.id:
                cons_shift = nurse_hist.numberOfConsecutiveAssignments
            for day in range(total_days):
                if schedule[day] is not None and schedule[day][0] == st.id:
                    cons_shift += 1
                else:
                    if cons_shift > 0:
                        if cons_shift < st.minimumNumberOfConsecutiveAssignments:
                            cost += 15 * (
                                st.minimumNumberOfConsecutiveAssignments - cons_shift
                            )
                        if cons_shift > st.maximumNumberOfConsecutiveAssignments:
                            cost += 15 * (
                                cons_shift - st.maximumNumberOfConsecutiveAssignments
                            )
                    cons_shift = 0
            if cons_shift > st.maximumNumberOfConsecutiveAssignments:
                cost += 15 * (cons_shift - st.maximumNumberOfConsecutiveAssignments)

        # Working weekends
        working_weekends = nurse_hist.numberOfWorkingWeekends
        for week_idx in range(num_weeks):
            sat = week_idx * 7 + 5
            sun = week_idx * 7 + 6
            if schedule[sat] is not None or schedule[sun] is not None:
                working_weekends += 1

        if working_weekends > contract.maximumNumberOfWorkingWeekends:
            cost += 30 * (working_weekends - contract.maximumNumberOfWorkingWeekends)

        # Complete weekends
        if contract.completeWeekends:
            for week_idx in range(num_weeks):
                sat = week_idx * 7 + 5
                sun = week_idx * 7 + 6
                sat_works = schedule[sat] is not None
                sun_works = schedule[sun] is not None
                if sat_works != sun_works:
                    cost += 30

    return cost
