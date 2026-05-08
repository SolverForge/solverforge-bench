import json
import time
from collections import defaultdict
from typing import Any

from ortools.sat.python import cp_model

from employee_scheduling_bench.domain.models import Assignment, Instance, Solution
from employee_scheduling_bench.domain.validation import validate
from employee_scheduling_bench.solver.instance_json import serialize_instance

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ANY_SHIFT_TYPE = 2**64 - 1


def solve_with_ortools(instance: Instance, time_limit: int) -> Solution:
    payload = json.loads(serialize_instance(instance))
    nurses = payload["nurses"]
    contracts = payload["contracts"]
    shift_types = payload["shift_types"]
    shifts = payload["shifts"]
    histories = sorted(payload["nurse_history"], key=lambda h: h["nurse_idx"])
    num_nurses = len(nurses)
    num_weeks = payload["num_weeks"]
    total_days = num_weeks * 7

    forbidden_successors: dict[int, set[int]] = defaultdict(set)
    for entry in payload["forbidden"]:
        forbidden_successors[entry["preceding"]].update(entry["succeeding"])

    seed_time_limit = min(5.0, max(1.0, float(time_limit) * 0.25))
    seed_time_limit = min(seed_time_limit, float(time_limit))
    seed_start = time.monotonic()
    hard_seed = _solve_hard_seed(
        payload,
        forbidden_successors,
        seed_time_limit,
    )
    seed_elapsed = time.monotonic() - seed_start
    remaining_time = float(time_limit) - seed_elapsed
    if hard_seed is not None and remaining_time <= 0.1:
        return _solution_from_assignment_keys(instance, payload, hard_seed)

    model = cp_model.CpModel()

    requests_by_nurse_day: dict[tuple[int, int], list[int]] = defaultdict(list)
    for request in payload["shift_off_requests"]:
        requests_by_nurse_day[(request["nurse_idx"], request["global_day"])].append(
            request["shift_type_idx"]
        )

    objective_terms: list[Any] = []
    assignment_vars: dict[tuple[int, int], cp_model.IntVar] = {}
    unassigned_vars: dict[int, cp_model.IntVar] = {}
    vars_by_nurse: dict[int, list[cp_model.IntVar]] = defaultdict(list)
    vars_by_nurse_day: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    vars_by_nurse_day_shift_type: dict[tuple[int, int, int], list[cp_model.IntVar]] = (
        defaultdict(list)
    )

    for shift_idx, shift in enumerate(shifts):
        global_day = _global_day(shift)
        candidates = []
        for nurse_idx, nurse in enumerate(nurses):
            if shift["skill_idx"] not in nurse["skills"]:
                continue
            history_last_shift = histories[nurse_idx]["last_shift_type_idx"]
            if (
                global_day == 0
                and history_last_shift is not None
                and shift["shift_type_idx"] in forbidden_successors[history_last_shift]
            ):
                continue
            var = model.NewBoolVar(f"assign_s{shift_idx}_n{nurse_idx}")
            candidates.append(var)
            assignment_vars[(shift_idx, nurse_idx)] = var
            vars_by_nurse[nurse_idx].append(var)
            vars_by_nurse_day[(nurse_idx, global_day)].append(var)
            vars_by_nurse_day_shift_type[
                (nurse_idx, global_day, shift["shift_type_idx"])
            ].append(var)

            request_count = sum(
                1
                for requested_shift_type in requests_by_nurse_day[
                    (nurse_idx, global_day)
                ]
                if requested_shift_type == ANY_SHIFT_TYPE
                or requested_shift_type == shift["shift_type_idx"]
            )
            if request_count:
                objective_terms.append(request_count * 10 * var)

        if shift["is_minimum"]:
            model.Add(sum(candidates) == 1)
        else:
            model.Add(sum(candidates) <= 1)
            unassigned = model.NewBoolVar(f"optional_unassigned_s{shift_idx}")
            unassigned_vars[shift_idx] = unassigned
            model.Add(unassigned + sum(candidates) == 1)
            objective_terms.append(30 * unassigned)

    work_by_nurse_day: dict[tuple[int, int], cp_model.IntVar] = {}
    shift_type_by_nurse_day: dict[tuple[int, int, int], cp_model.IntVar] = {}
    for nurse_idx in range(num_nurses):
        for day in range(total_days):
            work = model.NewBoolVar(f"work_n{nurse_idx}_d{day}")
            model.Add(work == sum(vars_by_nurse_day[(nurse_idx, day)]))
            work_by_nurse_day[(nurse_idx, day)] = work

            for shift_type_idx in range(len(shift_types)):
                works_type = model.NewBoolVar(
                    f"work_n{nurse_idx}_d{day}_st{shift_type_idx}"
                )
                model.Add(
                    works_type
                    == sum(
                        vars_by_nurse_day_shift_type[(nurse_idx, day, shift_type_idx)]
                    )
                )
                shift_type_by_nurse_day[(nurse_idx, day, shift_type_idx)] = works_type

    for nurse_idx in range(num_nurses):
        for day in range(total_days):
            model.Add(sum(vars_by_nurse_day[(nurse_idx, day)]) <= 1)

        for day in range(total_days - 1):
            for preceding, successors in forbidden_successors.items():
                for succeeding in successors:
                    for left in vars_by_nurse_day_shift_type[
                        (nurse_idx, day, preceding)
                    ]:
                        for right in vars_by_nurse_day_shift_type[
                            (nurse_idx, day + 1, succeeding)
                        ]:
                            model.Add(left + right <= 1)

    for nurse_idx, nurse in enumerate(nurses):
        contract = contracts[nurse["contract_idx"]]
        history = histories[nurse_idx]
        assignment_count = sum(vars_by_nurse[nurse_idx])
        total_assignment_upper = history["num_assignments"] + len(shifts)

        under_assignments = model.NewIntVar(
            0, total_assignment_upper, f"under_assignments_n{nurse_idx}"
        )
        model.Add(
            under_assignments
            >= contract["min_assignments"]
            - history["num_assignments"]
            - assignment_count
        )
        objective_terms.append(20 * under_assignments)

        over_assignments = model.NewIntVar(
            0, total_assignment_upper, f"over_assignments_n{nurse_idx}"
        )
        model.Add(
            over_assignments
            >= history["num_assignments"]
            + assignment_count
            - contract["max_assignments"]
        )
        objective_terms.append(20 * over_assignments)

        work_sequence = [
            work_by_nurse_day[(nurse_idx, day)] for day in range(total_days)
        ]
        _add_run_length_costs(
            model=model,
            active_by_day=work_sequence,
            history_active=history["last_shift_type_idx"] is not None,
            history_length=history["num_consecutive_working"],
            min_length=contract["min_consecutive_working"],
            max_length=contract["max_consecutive_working"],
            weight=30,
            name=f"work_n{nurse_idx}",
            objective_terms=objective_terms,
        )
        _add_run_length_costs(
            model=model,
            active_by_day=[day_work.Not() for day_work in work_sequence],
            history_active=history["last_shift_type_idx"] is None,
            history_length=history["num_consecutive_off"],
            min_length=contract["min_consecutive_off"],
            max_length=contract["max_consecutive_off"],
            weight=30,
            name=f"off_n{nurse_idx}",
            objective_terms=objective_terms,
        )

        for shift_type_idx, shift_type in enumerate(shift_types):
            _add_run_length_costs(
                model=model,
                active_by_day=[
                    shift_type_by_nurse_day[(nurse_idx, day, shift_type_idx)]
                    for day in range(total_days)
                ],
                history_active=history["last_shift_type_idx"] == shift_type_idx,
                history_length=history["num_consecutive_assignments"],
                min_length=shift_type["min_consecutive"],
                max_length=shift_type["max_consecutive"],
                weight=15,
                name=f"shift_type_n{nurse_idx}_st{shift_type_idx}",
                objective_terms=objective_terms,
            )

        weekend_terms = []
        for week in range(num_weeks):
            saturday = work_by_nurse_day[(nurse_idx, week * 7 + 5)]
            sunday = work_by_nurse_day[(nurse_idx, week * 7 + 6)]
            weekend = model.NewBoolVar(f"weekend_n{nurse_idx}_w{week}")
            model.AddMaxEquality(weekend, [saturday, sunday])
            weekend_terms.append(weekend)

            if contract["complete_weekends"]:
                incomplete = model.NewBoolVar(
                    f"incomplete_weekend_n{nurse_idx}_w{week}"
                )
                model.AddAbsEquality(incomplete, saturday - sunday)
                objective_terms.append(30 * incomplete)

        over_weekends = model.NewIntVar(
            0,
            num_weeks + history["num_working_weekends"],
            f"over_weekends_n{nurse_idx}",
        )
        model.Add(
            over_weekends
            >= history["num_working_weekends"]
            + sum(weekend_terms)
            - contract["max_working_weekends"]
        )
        objective_terms.append(30 * over_weekends)

    hint = (
        hard_seed
        if hard_seed is not None
        else _build_greedy_hint(payload, forbidden_successors)
    )
    for key, var in assignment_vars.items():
        model.AddHint(var, 1 if key in hint else 0)
    hinted_shift_indices = {shift_idx for shift_idx, _ in hint}
    for shift_idx, var in unassigned_vars.items():
        model.AddHint(var, 0 if shift_idx in hinted_shift_indices else 1)
    for (nurse_idx, day), var in work_by_nurse_day.items():
        works = any(
            (shift_idx, nurse_idx) in hint and _global_day(shifts[shift_idx]) == day
            for shift_idx, _ in hint
        )
        model.AddHint(var, int(works))
    for (nurse_idx, day, shift_type_idx), var in shift_type_by_nurse_day.items():
        works_type = any(
            (shift_idx, nurse_idx) in hint
            and _global_day(shifts[shift_idx]) == day
            and shifts[shift_idx]["shift_type_idx"] == shift_type_idx
            for shift_idx, _ in hint
        )
        model.AddHint(var, int(works_type))

    model.Minimize(sum(objective_terms) if objective_terms else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.1, remaining_time)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 1
    solver.parameters.log_search_progress = False
    solver.parameters.repair_hint = True
    solver.parameters.hint_conflict_limit = 100_000

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if hard_seed is not None:
            return _solution_from_assignment_keys(instance, payload, hard_seed)
        raise RuntimeError(
            f"OR-Tools CP-SAT failed with status {solver.StatusName(status)}"
        )

    assignment_keys = {
        key for key, var in assignment_vars.items() if solver.BooleanValue(var)
    }
    solution = Solution(
        assignments=_weekly_assignments_from_keys(payload, assignment_keys)
    )
    solution.cost = validate(solution, instance)
    return solution


def _global_day(shift: dict[str, Any]) -> int:
    return shift["week"] * 7 + shift["day"]


def _build_greedy_hint(
    payload: dict[str, Any],
    forbidden_successors: dict[int, set[int]],
) -> set[tuple[int, int]]:
    nurses = payload["nurses"]
    histories = sorted(payload["nurse_history"], key=lambda h: h["nurse_idx"])
    total_days = payload["num_weeks"] * 7
    assigned_shift_type_by_nurse_day: list[list[int | None]] = [
        [None] * total_days for _ in nurses
    ]
    assignment_count_by_nurse = [0] * len(nurses)
    hint: set[tuple[int, int]] = set()

    shifts_with_index = sorted(
        enumerate(payload["shifts"]),
        key=lambda item: (
            item[1]["week"],
            item[1]["day"],
            not item[1]["is_minimum"],
            item[1]["shift_type_idx"],
            item[1]["skill_idx"],
            item[0],
        ),
    )
    for shift_idx, shift in shifts_with_index:
        if not shift["is_minimum"]:
            continue
        global_day = _global_day(shift)
        candidates = []
        for nurse_idx, nurse in enumerate(nurses):
            if shift["skill_idx"] not in nurse["skills"]:
                continue
            if assigned_shift_type_by_nurse_day[nurse_idx][global_day] is not None:
                continue
            previous_shift_type = _previous_shift_type(
                assigned_shift_type_by_nurse_day[nurse_idx],
                histories[nurse_idx],
                global_day,
            )
            if (
                previous_shift_type is not None
                and shift["shift_type_idx"] in forbidden_successors[previous_shift_type]
            ):
                continue
            next_shift_type = _next_shift_type(
                assigned_shift_type_by_nurse_day[nurse_idx],
                global_day,
            )
            if (
                next_shift_type is not None
                and next_shift_type in forbidden_successors[shift["shift_type_idx"]]
            ):
                continue
            candidates.append(nurse_idx)

        if not candidates:
            continue
        nurse_idx = min(candidates, key=lambda idx: assignment_count_by_nurse[idx])
        assigned_shift_type_by_nurse_day[nurse_idx][global_day] = shift[
            "shift_type_idx"
        ]
        assignment_count_by_nurse[nurse_idx] += 1
        hint.add((shift_idx, nurse_idx))

    return hint


def _solve_hard_seed(
    payload: dict[str, Any],
    forbidden_successors: dict[int, set[int]],
    time_limit: float,
) -> set[tuple[int, int]] | None:
    model = cp_model.CpModel()
    histories = sorted(payload["nurse_history"], key=lambda h: h["nurse_idx"])
    assignment_vars: dict[tuple[int, int], cp_model.IntVar] = {}
    vars_by_nurse_day: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    vars_by_nurse_day_shift_type: dict[tuple[int, int, int], list[cp_model.IntVar]] = (
        defaultdict(list)
    )

    for shift_idx, shift in enumerate(payload["shifts"]):
        global_day = _global_day(shift)
        candidates = []
        for nurse_idx, nurse in enumerate(payload["nurses"]):
            if shift["skill_idx"] not in nurse["skills"]:
                continue
            history_last_shift = histories[nurse_idx]["last_shift_type_idx"]
            if (
                global_day == 0
                and history_last_shift is not None
                and shift["shift_type_idx"] in forbidden_successors[history_last_shift]
            ):
                continue
            var = model.NewBoolVar(f"seed_s{shift_idx}_n{nurse_idx}")
            candidates.append(var)
            assignment_vars[(shift_idx, nurse_idx)] = var
            vars_by_nurse_day[(nurse_idx, global_day)].append(var)
            vars_by_nurse_day_shift_type[
                (nurse_idx, global_day, shift["shift_type_idx"])
            ].append(var)

        if shift["is_minimum"]:
            model.Add(sum(candidates) == 1)
        else:
            model.Add(sum(candidates) == 0)

    total_days = payload["num_weeks"] * 7
    for nurse_idx in range(len(payload["nurses"])):
        for day in range(total_days):
            model.Add(sum(vars_by_nurse_day[(nurse_idx, day)]) <= 1)

        for day in range(total_days - 1):
            for preceding, successors in forbidden_successors.items():
                for succeeding in successors:
                    for left in vars_by_nurse_day_shift_type[
                        (nurse_idx, day, preceding)
                    ]:
                        for right in vars_by_nurse_day_shift_type[
                            (nurse_idx, day + 1, succeeding)
                        ]:
                            model.Add(left + right <= 1)

    greedy_hint = _build_greedy_hint(payload, forbidden_successors)
    for key, var in assignment_vars.items():
        model.AddHint(var, 1 if key in greedy_hint else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 1
    solver.parameters.log_search_progress = False
    solver.parameters.repair_hint = True
    solver.parameters.hint_conflict_limit = 100_000
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return {key for key, var in assignment_vars.items() if solver.BooleanValue(var)}


def _solution_from_assignment_keys(
    instance: Instance,
    payload: dict[str, Any],
    assignment_keys: set[tuple[int, int]],
) -> Solution:
    solution = Solution(
        assignments=_weekly_assignments_from_keys(payload, assignment_keys)
    )
    solution.cost = validate(solution, instance)
    return solution


def _weekly_assignments_from_keys(
    payload: dict[str, Any],
    assignment_keys: set[tuple[int, int]],
) -> list[list[Assignment]]:
    weekly: list[list[Assignment]] = [[] for _ in range(payload["num_weeks"])]
    for shift_idx, nurse_idx in sorted(assignment_keys):
        shift = payload["shifts"][shift_idx]
        weekly[shift["week"]].append(
            Assignment(
                nurse=payload["nurse_names"][nurse_idx],
                day=DAYS[shift["day"]],
                shiftType=payload["shift_type_names"][shift["shift_type_idx"]],
                skill=payload["skill_names"][shift["skill_idx"]],
            )
        )
    return weekly


def _previous_shift_type(
    assigned_shift_type_by_day: list[int | None],
    history: dict[str, Any],
    global_day: int,
) -> int | None:
    if global_day == 0:
        return history["last_shift_type_idx"]
    return assigned_shift_type_by_day[global_day - 1]


def _next_shift_type(
    assigned_shift_type_by_day: list[int | None],
    global_day: int,
) -> int | None:
    if global_day + 1 >= len(assigned_shift_type_by_day):
        return None
    return assigned_shift_type_by_day[global_day + 1]


def _add_run_length_costs(
    *,
    model: cp_model.CpModel,
    active_by_day: list[Any],
    history_active: bool,
    history_length: int,
    min_length: int,
    max_length: int,
    weight: int,
    name: str,
    objective_terms: list[Any],
) -> None:
    if not active_by_day:
        return

    max_possible_length = len(active_by_day) + max(0, history_length)
    closed_costs = [
        _closed_bounds_cost(length, min_length, max_length, weight)
        for length in range(max_possible_length + 1)
    ]
    max_costs = [
        _max_bound_cost(length, max_length, weight)
        for length in range(max_possible_length + 1)
    ]
    max_closed_cost = max(closed_costs)
    max_end_cost = max(max_costs)

    run_lengths = []
    for day, active in enumerate(active_by_day):
        run_length = model.NewIntVar(0, max_possible_length, f"{name}_run_len_d{day}")
        if day == 0:
            active_length = history_length + 1 if history_active else 1
            model.Add(run_length == active_length).OnlyEnforceIf(active)
            model.Add(run_length == 0).OnlyEnforceIf(active.Not())
        else:
            previous_active = active_by_day[day - 1]
            previous_run_length = run_lengths[-1]
            model.Add(run_length == 0).OnlyEnforceIf(active.Not())
            model.Add(run_length == 1).OnlyEnforceIf([active, previous_active.Not()])
            model.Add(run_length == previous_run_length + 1).OnlyEnforceIf(
                [active, previous_active]
            )
        run_lengths.append(run_length)

    if history_active and history_length > 0:
        immediate_cost = _closed_bounds_cost(
            history_length, min_length, max_length, weight
        )
        if immediate_cost:
            objective_terms.append(immediate_cost * active_by_day[0].Not())

    for day in range(1, len(active_by_day)):
        previous_active = active_by_day[day - 1]
        current_active = active_by_day[day]
        closes = _and_literal(
            model,
            [previous_active, current_active.Not()],
            f"{name}_closes_before_d{day}",
        )
        raw_cost = model.NewIntVar(0, max_closed_cost, f"{name}_closed_raw_d{day}")
        penalty = model.NewIntVar(0, max_closed_cost, f"{name}_closed_penalty_d{day}")
        model.AddElement(run_lengths[day - 1], closed_costs, raw_cost)
        model.Add(penalty == raw_cost).OnlyEnforceIf(closes)
        model.Add(penalty == 0).OnlyEnforceIf(closes.Not())
        objective_terms.append(penalty)

    end_cost = model.NewIntVar(0, max_end_cost, f"{name}_end_raw")
    end_penalty = model.NewIntVar(0, max_end_cost, f"{name}_end_penalty")
    model.AddElement(run_lengths[-1], max_costs, end_cost)
    model.Add(end_penalty == end_cost).OnlyEnforceIf(active_by_day[-1])
    model.Add(end_penalty == 0).OnlyEnforceIf(active_by_day[-1].Not())
    objective_terms.append(end_penalty)


def _and_literal(
    model: cp_model.CpModel,
    literals: list[Any],
    name: str,
) -> cp_model.IntVar:
    combined = model.NewBoolVar(name)
    for literal in literals:
        model.AddImplication(combined, literal)
    model.AddBoolOr([literal.Not() for literal in literals] + [combined])
    return combined


def _closed_bounds_cost(
    length: int, min_length: int, max_length: int, weight: int
) -> int:
    if length == 0:
        return 0
    cost = 0
    if length < min_length:
        cost += weight * (min_length - length)
    if length > max_length:
        cost += weight * (length - max_length)
    return cost


def _max_bound_cost(length: int, max_length: int, weight: int) -> int:
    if length > max_length:
        return weight * (length - max_length)
    return 0
