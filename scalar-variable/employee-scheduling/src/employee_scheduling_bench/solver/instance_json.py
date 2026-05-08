import json

from employee_scheduling_bench.domain.models import Instance

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def serialize_instance(instance: Instance) -> str:
    scenario = instance.scenario
    skill_idx = {s: i for i, s in enumerate(scenario.skills)}
    shift_type_idx = {st.id: i for i, st in enumerate(scenario.shiftTypes)}
    contract_idx = {c.id: i for i, c in enumerate(scenario.contracts)}
    nurse_idx = {n.id: i for i, n in enumerate(scenario.nurses)}

    nurses = []
    for n in scenario.nurses:
        nurses.append(
            {
                "id": n.id,
                "contract_idx": contract_idx[n.contract],
                "skills": [skill_idx[s] for s in n.skills],
            }
        )

    contracts = []
    for c in scenario.contracts:
        contracts.append(
            {
                "id": c.id,
                "min_assignments": c.minimumNumberOfAssignments,
                "max_assignments": c.maximumNumberOfAssignments,
                "min_consecutive_working": c.minimumNumberOfConsecutiveWorkingDays,
                "max_consecutive_working": c.maximumNumberOfConsecutiveWorkingDays,
                "min_consecutive_off": c.minimumNumberOfConsecutiveDaysOff,
                "max_consecutive_off": c.maximumNumberOfConsecutiveDaysOff,
                "max_working_weekends": c.maximumNumberOfWorkingWeekends,
                "complete_weekends": bool(c.completeWeekends),
            }
        )

    shift_types = []
    for st in scenario.shiftTypes:
        shift_types.append(
            {
                "id": st.id,
                "min_consecutive": st.minimumNumberOfConsecutiveAssignments,
                "max_consecutive": st.maximumNumberOfConsecutiveAssignments,
            }
        )

    forbidden = []
    for f in scenario.forbiddenShiftTypeSuccessions:
        forbidden.append(
            {
                "preceding": shift_type_idx[f.precedingShiftType],
                "succeeding": [shift_type_idx[s] for s in f.succeedingShiftTypes],
            }
        )

    shift_off_requests = []
    for week_idx, week_data in enumerate(instance.weeks):
        for req in week_data.shiftOffRequests:
            day_offset = DAYS.index(req.day)
            global_day = week_idx * 7 + day_offset
            shift_off_requests.append(
                {
                    "nurse_idx": nurse_idx[req.nurse],
                    "global_day": global_day,
                    "shift_type_idx": shift_type_idx.get(req.shiftType, 2**64 - 1),
                }
            )

    nurse_history = []
    for nh in instance.history.nurseHistory:
        last_st = None
        if nh.lastAssignedShiftType != "None":
            last_st = shift_type_idx.get(nh.lastAssignedShiftType)
        nurse_history.append(
            {
                "nurse_idx": nurse_idx[nh.nurse],
                "num_assignments": nh.numberOfAssignments,
                "num_working_weekends": nh.numberOfWorkingWeekends,
                "last_shift_type_idx": last_st,
                "num_consecutive_assignments": nh.numberOfConsecutiveAssignments,
                "num_consecutive_working": nh.numberOfConsecutiveWorkingDays,
                "num_consecutive_off": nh.numberOfConsecutiveDaysOff,
            }
        )

    shifts = []
    for week_idx, week_data in enumerate(instance.weeks):
        for req in week_data.requirements:
            for day_idx, day_req in enumerate(
                [
                    req.requirementOnMonday,
                    req.requirementOnTuesday,
                    req.requirementOnWednesday,
                    req.requirementOnThursday,
                    req.requirementOnFriday,
                    req.requirementOnSaturday,
                    req.requirementOnSunday,
                ]
            ):
                for slot in range(day_req.optimal):
                    shifts.append(
                        {
                            "week": week_idx,
                            "day": day_idx,
                            "shift_type_idx": shift_type_idx[req.shiftType],
                            "skill_idx": skill_idx[req.skill],
                            "is_minimum": slot < day_req.minimum,
                        }
                    )

    return json.dumps(
        {
            "nurses": nurses,
            "contracts": contracts,
            "shift_types": shift_types,
            "forbidden": forbidden,
            "shift_off_requests": shift_off_requests,
            "nurse_history": nurse_history,
            "shifts": shifts,
            "num_weeks": len(instance.weeks),
            "skill_names": scenario.skills,
            "shift_type_names": [st.id for st in scenario.shiftTypes],
            "nurse_names": [n.id for n in scenario.nurses],
        }
    )
