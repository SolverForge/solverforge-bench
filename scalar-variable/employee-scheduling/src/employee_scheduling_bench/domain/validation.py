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
    return sum(validate_breakdown(solution=solution, instance=instance).values())


def validate_breakdown(solution: Solution, instance: Instance) -> dict[str, int]:
    """Return INRC-II soft costs by constraint name after hard validation."""
    scenario = instance.scenario
    nurse_by_id = {n.id: n for n in scenario.nurses}
    contract_by_id = {c.id: c for c in scenario.contracts}
    forbidden = {
        f.precedingShiftType: set(f.succeedingShiftTypes)
        for f in scenario.forbiddenShiftTypeSuccessions
    }

    num_weeks = len(solution.assignments)
    total_days = num_weeks * 7
    nurse_schedule: dict[str, list[tuple[str, str] | None]] = {
        n.id: [None] * total_days for n in scenario.nurses
    }

    for week_idx, week_assignments in enumerate(solution.assignments):
        for assignment in week_assignments:
            day_offset = DAYS.index(assignment.day)
            global_day = week_idx * 7 + day_offset

            if nurse_schedule[assignment.nurse][global_day] is not None:
                raise SingleAssignmentViolation(
                    f"Nurse {assignment.nurse} has multiple assignments on week {week_idx} "
                    f"{assignment.day}"
                )
            nurse_schedule[assignment.nurse][global_day] = (
                assignment.shiftType,
                assignment.skill,
            )

            nurse = nurse_by_id[assignment.nurse]
            if assignment.skill not in nurse.skills:
                raise MissingSkillViolation(
                    f"Nurse {assignment.nurse} lacks skill {assignment.skill} "
                    f"for assignment on {assignment.day}"
                )

    for week_idx, week_data in enumerate(instance.weeks):
        coverage: dict[tuple[str, str, str], int] = {}
        for assignment in solution.assignments[week_idx]:
            key = (assignment.shiftType, assignment.skill, assignment.day)
            coverage[key] = coverage.get(key, 0) + 1

        for req in week_data.requirements:
            for day_name, day_req in _day_requirements(req):
                actual = coverage.get((req.shiftType, req.skill, day_name), 0)
                if actual < day_req.minimum:
                    raise MinCoverageViolation(
                        f"Week {week_idx} {day_name}: {req.shiftType}/{req.skill} "
                        f"has {actual} nurses, minimum is {day_req.minimum}"
                    )

    for nurse_id, schedule in nurse_schedule.items():
        nurse_hist = next(
            nh for nh in instance.history.nurseHistory if nh.nurse == nurse_id
        )
        last_shift = nurse_hist.lastAssignedShiftType

        for day in range(total_days):
            if schedule[day] is None:
                continue
            current_shift = schedule[day][0]
            prev_shift = (
                last_shift
                if day == 0
                else (schedule[day - 1][0] if schedule[day - 1] is not None else None)
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

    breakdown = {
        "optimalCoverage": 0,
        "shiftOffRequests": 0,
        "totalAssignmentBounds": 0,
        "consecutiveWorkBounds": 0,
        "consecutiveOffBounds": 0,
        "consecutiveShiftTypeBounds": 0,
        "workingWeekends": 0,
        "completeWeekends": 0,
    }

    for week_idx, week_data in enumerate(instance.weeks):
        coverage: dict[tuple[str, str, str], int] = {}
        for assignment in solution.assignments[week_idx]:
            key = (assignment.shiftType, assignment.skill, assignment.day)
            coverage[key] = coverage.get(key, 0) + 1

        for req in week_data.requirements:
            for day_name, day_req in _day_requirements(req):
                actual = coverage.get((req.shiftType, req.skill, day_name), 0)
                if actual < day_req.optimal:
                    breakdown["optimalCoverage"] += 30 * (day_req.optimal - actual)

    for week_idx, week_data in enumerate(instance.weeks):
        for req in week_data.shiftOffRequests:
            day_offset = DAYS.index(req.day)
            global_day = week_idx * 7 + day_offset
            entry = nurse_schedule[req.nurse][global_day]
            if entry is not None and (
                req.shiftType == "Any" or entry[0] == req.shiftType
            ):
                breakdown["shiftOffRequests"] += 10

    for nurse_id, schedule in nurse_schedule.items():
        nurse = nurse_by_id[nurse_id]
        contract = contract_by_id[nurse.contract]
        nurse_hist = next(
            nh for nh in instance.history.nurseHistory if nh.nurse == nurse_id
        )

        total_assigned = sum(1 for entry in schedule if entry is not None)
        total_assigned += nurse_hist.numberOfAssignments
        if total_assigned < contract.minimumNumberOfAssignments:
            breakdown["totalAssignmentBounds"] += 20 * (
                contract.minimumNumberOfAssignments - total_assigned
            )
        elif total_assigned > contract.maximumNumberOfAssignments:
            breakdown["totalAssignmentBounds"] += 20 * (
                total_assigned - contract.maximumNumberOfAssignments
            )

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
                        breakdown["consecutiveWorkBounds"] += 30 * (
                            contract.minimumNumberOfConsecutiveWorkingDays - cons_work
                        )
                    if cons_work > contract.maximumNumberOfConsecutiveWorkingDays:
                        breakdown["consecutiveWorkBounds"] += 30 * (
                            cons_work - contract.maximumNumberOfConsecutiveWorkingDays
                        )
                cons_work = 0
        if cons_work > contract.maximumNumberOfConsecutiveWorkingDays:
            breakdown["consecutiveWorkBounds"] += 30 * (
                cons_work - contract.maximumNumberOfConsecutiveWorkingDays
            )

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
                        breakdown["consecutiveOffBounds"] += 30 * (
                            contract.minimumNumberOfConsecutiveDaysOff - cons_off
                        )
                    if cons_off > contract.maximumNumberOfConsecutiveDaysOff:
                        breakdown["consecutiveOffBounds"] += 30 * (
                            cons_off - contract.maximumNumberOfConsecutiveDaysOff
                        )
                cons_off = 0
        if cons_off > contract.maximumNumberOfConsecutiveDaysOff:
            breakdown["consecutiveOffBounds"] += 30 * (
                cons_off - contract.maximumNumberOfConsecutiveDaysOff
            )

        for shift_type in scenario.shiftTypes:
            cons_shift = (
                nurse_hist.numberOfConsecutiveAssignments
                if nurse_hist.lastAssignedShiftType == shift_type.id
                else 0
            )
            for day in range(total_days):
                if schedule[day] is not None and schedule[day][0] == shift_type.id:
                    cons_shift += 1
                else:
                    if cons_shift > 0:
                        if (
                            cons_shift
                            < shift_type.minimumNumberOfConsecutiveAssignments
                        ):
                            breakdown["consecutiveShiftTypeBounds"] += 15 * (
                                shift_type.minimumNumberOfConsecutiveAssignments
                                - cons_shift
                            )
                        if (
                            cons_shift
                            > shift_type.maximumNumberOfConsecutiveAssignments
                        ):
                            breakdown["consecutiveShiftTypeBounds"] += 15 * (
                                cons_shift
                                - shift_type.maximumNumberOfConsecutiveAssignments
                            )
                    cons_shift = 0
            if cons_shift > shift_type.maximumNumberOfConsecutiveAssignments:
                breakdown["consecutiveShiftTypeBounds"] += 15 * (
                    cons_shift - shift_type.maximumNumberOfConsecutiveAssignments
                )

        working_weekends = nurse_hist.numberOfWorkingWeekends
        for week_idx in range(num_weeks):
            sat = week_idx * 7 + 5
            sun = week_idx * 7 + 6
            if schedule[sat] is not None or schedule[sun] is not None:
                working_weekends += 1

        if working_weekends > contract.maximumNumberOfWorkingWeekends:
            breakdown["workingWeekends"] += 30 * (
                working_weekends - contract.maximumNumberOfWorkingWeekends
            )

        if contract.completeWeekends:
            for week_idx in range(num_weeks):
                sat = week_idx * 7 + 5
                sun = week_idx * 7 + 6
                sat_works = schedule[sat] is not None
                sun_works = schedule[sun] is not None
                if sat_works != sun_works:
                    breakdown["completeWeekends"] += 30

    return breakdown


def _day_requirements(req):
    return [
        ("Mon", req.requirementOnMonday),
        ("Tue", req.requirementOnTuesday),
        ("Wed", req.requirementOnWednesday),
        ("Thu", req.requirementOnThursday),
        ("Fri", req.requirementOnFriday),
        ("Sat", req.requirementOnSaturday),
        ("Sun", req.requirementOnSunday),
    ]
