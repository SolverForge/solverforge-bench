from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from solverforge import (
    ConstraintFactory,
    HardSoftScore,
    ScalarGroupLimits,
    Solver,
    constraint_provider,
    indexed_presence,
    joiner,
    planning_entity,
    planning_solution,
    planning_variable,
    problem_fact,
    scalar_assignment_group,
)

from employee_scheduling_bench.domain.models import Assignment, Instance, Solution
from employee_scheduling_bench.solver.instance_json import DAYS, serialize_instance
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import SolverResult
from solverforge_bench.solverforge_config import solver_config_for_time_limit


_SOLVER_CONFIG_PATH = Path(__file__).with_name("solverforge_py.toml")


def _nurse_candidates(shift: Any) -> list[int]:
    return [
        nurse_idx
        for nurse_idx, has_skill in enumerate(shift.nurse_has_skill)
        if bool(has_skill)
        and (int(shift.global_day) != 0 or bool(shift.history_allows[nurse_idx]))
    ]


def _nearby_nurse_candidates(shift: Any) -> list[int]:
    return _nurse_candidates(shift)


def _nearby_shift_candidates(shift: Any) -> list[int]:
    return list(shift.nearby_shift_indices)


def _shift_to_nurse_distance(shift: Any, nurse_idx: int) -> float:
    if int(nurse_idx) < 0 or int(nurse_idx) >= len(shift.nurse_has_skill):
        return float("inf")
    distance = 0.0 if bool(shift.nurse_has_skill[int(nurse_idx)]) else 10_000.0
    if int(nurse_idx) in shift.shift_off_request_nurse_set:
        distance += 100.0
    return distance


def _shift_to_shift_distance(left: Any, right: Any) -> float:
    day_distance = min(abs(int(left.global_day) - int(right.global_day)), 14)
    skill_distance = 0 if int(left.skill_idx) == int(right.skill_idx) else 4
    shift_type_distance = (
        0 if int(left.shift_type_idx) == int(right.shift_type_idx) else 2
    )
    return float(day_distance + skill_distance + shift_type_distance)


def _shift_assignment_required(solution: Any, entity_index: int) -> bool:
    return bool(solution.shifts[int(entity_index)].is_minimum)


def _shift_nurse_day_capacity_key(
    solution: Any, entity_index: int, nurse_idx: int
) -> int:
    shift = solution.shifts[int(entity_index)]
    return int(nurse_idx) * int(solution.total_days) + int(shift.global_day)


def _shift_assignment_rule(
    solution: Any,
    left_entity: int,
    left_nurse: int,
    right_entity: int,
    right_nurse: int,
) -> bool:
    if int(left_nurse) != int(right_nurse):
        return True
    left = solution.shifts[int(left_entity)]
    right = solution.shifts[int(right_entity)]
    left_day = int(left.global_day)
    right_day = int(right.global_day)
    if left_day + 1 == right_day:
        return int(left.shift_type_idx) not in set(right.forbidden_predecessors)
    if right_day + 1 == left_day:
        return int(right.shift_type_idx) not in set(left.forbidden_predecessors)
    return True


def _shift_position_key(solution: Any, entity_index: int) -> int:
    shift = solution.shifts[int(entity_index)]
    return (
        int(shift.global_day) * 10_000
        + int(shift.shift_type_idx) * 100
        + int(shift.skill_idx)
    )


def _shift_nurse_sequence_key(solution: Any, entity_index: int, nurse_idx: int) -> int:
    del nurse_idx
    return int(solution.shifts[int(entity_index)].global_day)


NurseSoftKey = tuple[
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    bool,
    int | None,
    int,
    int,
    int,
    int,
]
ShiftTypeRunKey = tuple[int, int, int, int, int, int | None, int]


@problem_fact
class NurseSoftFact:
    def __init__(self, key: NurseSoftKey) -> None:
        self.key = key


@problem_fact
class NurseShiftTypeFact:
    def __init__(self, key: ShiftTypeRunKey) -> None:
        self.key = key


@planning_entity
class NrpShift:
    nurse_idx = planning_variable(
        value_range_provider="nurse_indices",
        candidate_values=_nurse_candidates,
        nearby_value_candidates=_nearby_nurse_candidates,
        nearby_entity_candidates=_nearby_shift_candidates,
        nearby_value_distance_meter=_shift_to_nurse_distance,
        nearby_entity_distance_meter=_shift_to_shift_distance,
        allows_unassigned=True,
    )

    def __init__(
        self,
        *,
        shift_id: int,
        week: int,
        day: int,
        shift_type_idx: int,
        skill_idx: int,
        is_minimum: bool,
        nurse_has_skill: list[bool],
        history_allows: list[bool],
        forbidden_predecessors: list[int],
        shift_off_request_nurses: list[int],
        nurse_soft_keys: list[NurseSoftKey],
        shift_type_run_keys: list[ShiftTypeRunKey],
        nearby_shift_indices: list[int],
    ) -> None:
        self.shift_id = shift_id
        self.week = week
        self.day = day
        self.global_day = week * 7 + day
        self.shift_type_idx = shift_type_idx
        self.skill_idx = skill_idx
        self.is_minimum = is_minimum
        self.nurse_has_skill = nurse_has_skill
        self.history_allows = history_allows
        self.forbidden_predecessors = forbidden_predecessors
        self.shift_off_request_nurses = shift_off_request_nurses
        self.shift_off_request_nurse_set = set(shift_off_request_nurses)
        self.nurse_soft_keys = nurse_soft_keys
        self.shift_type_run_keys = shift_type_run_keys
        self.nearby_shift_indices = nearby_shift_indices
        self.nurse_idx: int | None = None


def _assigned(shift: Any) -> bool:
    return shift.nurse_idx is not None


def _lacks_skill(shift: Any) -> bool:
    return _assigned(shift) and not bool(shift.nurse_has_skill[shift.nurse_idx])


def _history_blocks(shift: Any) -> bool:
    return (
        _assigned(shift)
        and int(shift.global_day) == 0
        and not bool(shift.history_allows[shift.nurse_idx])
    )


def _same_nurse_day(left: Any, right: Any) -> bool:
    return (
        int(left.shift_id) < int(right.shift_id)
        and int(left.global_day) == int(right.global_day)
        and left.nurse_idx == right.nurse_idx
    )


def _forbidden_pair(left: Any, right: Any) -> bool:
    if int(left.shift_id) >= int(right.shift_id):
        return False
    left_day = int(left.global_day)
    right_day = int(right.global_day)
    if left_day + 1 == right_day:
        return int(left.shift_type_idx) in set(right.forbidden_predecessors)
    if right_day + 1 == left_day:
        return int(right.shift_type_idx) in set(left.forbidden_predecessors)
    return False


def _shift_off_cost(shift: Any) -> HardSoftScore:
    if shift.nurse_idx is None:
        return HardSoftScore.ZERO
    return HardSoftScore.of_soft(
        10
        * sum(
            1
            for request_nurse in shift.shift_off_request_nurses
            if int(request_nurse) == int(shift.nurse_idx)
        )
    )


def _nurse_soft_key(shift: Any) -> NurseSoftKey | None:
    if shift.nurse_idx is None:
        return None
    return shift.nurse_soft_keys[int(shift.nurse_idx)]


def _shift_type_run_key(shift: Any) -> ShiftTypeRunKey | None:
    if shift.nurse_idx is None:
        return None
    return shift.shift_type_run_keys[int(shift.nurse_idx)]


def _closed_bounds_cost(length: int, minimum: int, maximum: int, weight: int) -> int:
    if length == 0:
        return 0
    cost = 0
    if length < minimum:
        cost += weight * (minimum - length)
    if length > maximum:
        cost += weight * (length - maximum)
    return cost


def _max_bound_cost(length: int, maximum: int, weight: int) -> int:
    return weight * (length - maximum) if length > maximum else 0


def _run_bounds_cost(
    runs: Any,
    total_days: int,
    initial_run: int,
    minimum: int,
    maximum: int,
    weight: int,
) -> int:
    cost = 0
    initial_consumed = False
    for run in runs.runs():
        length = int(run.point_count())
        if not initial_consumed and initial_run > 0:
            if int(run.start()) == 0:
                length += initial_run
            else:
                cost += _closed_bounds_cost(initial_run, minimum, maximum, weight)
            initial_consumed = True
        if int(run.end()) + 1 >= total_days:
            cost += _max_bound_cost(length, maximum, weight)
        else:
            cost += _closed_bounds_cost(length, minimum, maximum, weight)
    if not initial_consumed and initial_run > 0:
        cost += _closed_bounds_cost(initial_run, minimum, maximum, weight)
    return cost


def _total_assignment_bounds_cost(key: NurseSoftKey, presence: Any | None) -> int:
    total_assigned = (int(presence.item_count()) if presence is not None else 0) + key[
        11
    ]
    if total_assigned < key[2]:
        return 20 * (key[2] - total_assigned)
    if total_assigned > key[3]:
        return 20 * (total_assigned - key[3])
    return 0


def _consecutive_work_bounds_cost(key: NurseSoftKey, presence: Any | None) -> int:
    if presence is None:
        return (
            _closed_bounds_cost(key[13], key[4], key[5], 30)
            if key[10] is not None
            else 0
        )
    initial = key[13] if key[10] is not None else 0
    return _run_bounds_cost(presence.runs(), key[1], initial, key[4], key[5], 30)


def _consecutive_off_bounds_cost(key: NurseSoftKey, presence: Any | None) -> int:
    if presence is None:
        initial = key[14] if key[10] is None else 0
        return _max_bound_cost(initial + key[1], key[7], 30)
    initial = key[14] if key[10] is None else 0
    return _run_bounds_cost(
        presence.complement_runs(0, key[1]),
        key[1],
        initial,
        key[6],
        key[7],
        30,
    )


def _consecutive_shift_type_bounds_cost(
    key: ShiftTypeRunKey, presence: Any | None
) -> int:
    if presence is None:
        return (
            _closed_bounds_cost(key[6], key[3], key[4], 15) if key[5] == key[1] else 0
        )
    initial = key[6] if key[5] == key[1] else 0
    return _run_bounds_cost(presence.runs(), key[2], initial, key[3], key[4], 15)


def _working_weekends_cost(key: NurseSoftKey, presence: Any | None) -> int:
    working_weekends = key[12]
    if presence is not None:
        for week in range(max(0, key[1]) // 7):
            saturday = week * 7 + 5
            if presence.any_in(saturday, saturday + 2):
                working_weekends += 1
    return _max_bound_cost(working_weekends, key[8], 30)


def _complete_weekends_cost(key: NurseSoftKey, presence: Any) -> int:
    if not key[9]:
        return 0
    cost = 0
    for week in range(max(0, key[1]) // 7):
        saturday = week * 7 + 5
        sat_works = presence.contains(saturday)
        sun_works = presence.contains(saturday + 1)
        if sat_works != sun_works:
            cost += 30
    return cost


def _nurse_delta(
    key: NurseSoftKey,
    presence: Any,
    cost_fn: Any,
) -> HardSoftScore:
    return HardSoftScore.of_soft(cost_fn(key, presence) - cost_fn(key, None))


def _shift_type_delta(
    key: ShiftTypeRunKey,
    presence: Any,
    cost_fn: Any,
) -> HardSoftScore:
    return HardSoftScore.of_soft(cost_fn(key, presence) - cost_fn(key, None))


@constraint_provider
def _nrp_constraints(factory: ConstraintFactory) -> list[object]:
    return [
        factory.for_each(NrpShift)
        .filter(lambda shift: shift.nurse_idx is None and shift.is_minimum)
        .penalize(HardSoftScore.of_hard(1000))
        .named("minimum coverage"),
        factory.for_each(NrpShift)
        .filter(lambda shift: shift.nurse_idx is None and not shift.is_minimum)
        .penalize(HardSoftScore.of_soft(30))
        .named("optimal coverage"),
        factory.for_each(NrpShift)
        .filter(_assigned)
        .join(joiner.equal(lambda shift: shift.nurse_idx))
        .filter(_same_nurse_day)
        .penalize(HardSoftScore.of_hard(1))
        .named("single assignment per day"),
        factory.for_each(NrpShift)
        .filter(_lacks_skill)
        .penalize(HardSoftScore.of_hard(1))
        .named("required skill"),
        factory.for_each(NrpShift)
        .filter(_history_blocks)
        .penalize(HardSoftScore.of_hard(1))
        .named("history forbidden succession"),
        factory.for_each(NrpShift)
        .filter(_assigned)
        .join(joiner.equal(lambda shift: shift.nurse_idx))
        .filter(_forbidden_pair)
        .penalize(HardSoftScore.of_hard(1))
        .named("adjacent forbidden succession"),
        factory.for_each(NrpShift)
        .filter(
            lambda shift: _assigned(shift)
            and shift.nurse_idx in shift.shift_off_request_nurses
        )
        .penalize(_shift_off_cost)
        .named("shift off requests"),
        factory.for_each(NurseSoftFact)
        .penalize(
            lambda fact: HardSoftScore.of_soft(
                _total_assignment_bounds_cost(fact.key, None)
            )
        )
        .named("empty total assignment bounds"),
        factory.for_each(NrpShift)
        .filter(_assigned)
        .group_by(_nurse_soft_key, indexed_presence(lambda shift: shift.global_day))
        .penalize(
            lambda key, presence: _nurse_delta(
                key, presence, _total_assignment_bounds_cost
            )
        )
        .named("total assignment bounds"),
        factory.for_each(NurseSoftFact)
        .penalize(
            lambda fact: HardSoftScore.of_soft(
                _consecutive_work_bounds_cost(fact.key, None)
            )
        )
        .named("empty consecutive work bounds"),
        factory.for_each(NrpShift)
        .filter(_assigned)
        .group_by(_nurse_soft_key, indexed_presence(lambda shift: shift.global_day))
        .penalize(
            lambda key, presence: _nurse_delta(
                key, presence, _consecutive_work_bounds_cost
            )
        )
        .named("consecutive work bounds"),
        factory.for_each(NurseSoftFact)
        .penalize(
            lambda fact: HardSoftScore.of_soft(
                _consecutive_off_bounds_cost(fact.key, None)
            )
        )
        .named("empty consecutive off bounds"),
        factory.for_each(NrpShift)
        .filter(_assigned)
        .group_by(_nurse_soft_key, indexed_presence(lambda shift: shift.global_day))
        .penalize(
            lambda key, presence: _nurse_delta(
                key, presence, _consecutive_off_bounds_cost
            )
        )
        .named("consecutive off bounds"),
        factory.for_each(NurseShiftTypeFact)
        .penalize(
            lambda fact: HardSoftScore.of_soft(
                _consecutive_shift_type_bounds_cost(fact.key, None)
            )
        )
        .named("empty consecutive shift type bounds"),
        factory.for_each(NrpShift)
        .filter(_assigned)
        .group_by(_shift_type_run_key, indexed_presence(lambda shift: shift.global_day))
        .penalize(
            lambda key, presence: _shift_type_delta(
                key, presence, _consecutive_shift_type_bounds_cost
            )
        )
        .named("consecutive shift type bounds"),
        factory.for_each(NurseSoftFact)
        .penalize(
            lambda fact: HardSoftScore.of_soft(_working_weekends_cost(fact.key, None))
        )
        .named("empty working weekends"),
        factory.for_each(NrpShift)
        .filter(_assigned)
        .group_by(_nurse_soft_key, indexed_presence(lambda shift: shift.global_day))
        .penalize(
            lambda key, presence: _nurse_delta(key, presence, _working_weekends_cost)
        )
        .named("working weekends"),
        factory.for_each(NrpShift)
        .filter(_assigned)
        .group_by(_nurse_soft_key, indexed_presence(lambda shift: shift.global_day))
        .penalize(
            lambda key, presence: HardSoftScore.of_soft(
                _complete_weekends_cost(key, presence)
            )
        )
        .named("complete weekends"),
    ]


@planning_solution(
    score=HardSoftScore,
    constraints=_nrp_constraints,
    scalar_groups=[
        scalar_assignment_group(
            "shift_nurse_assignment",
            entity_class="NrpShift",
            variable_name="nurse_idx",
            required_entity=_shift_assignment_required,
            capacity_key=_shift_nurse_day_capacity_key,
            assignment_rule=_shift_assignment_rule,
            position_key=_shift_position_key,
            sequence_key=_shift_nurse_sequence_key,
            sync_solution_before_callbacks=False,
            limits=ScalarGroupLimits(max_augmenting_depth=4, max_rematch_size=8),
        )
    ],
)
class NrpPythonPlan:
    shifts: list[NrpShift]
    nurse_soft_facts: list[NurseSoftFact]
    nurse_shift_type_facts: list[NurseShiftTypeFact]

    def __init__(self, payload: dict[str, Any]) -> None:
        nurses = payload["nurses"]
        forbidden_successors = _forbidden_successors(payload["forbidden"])
        history_by_nurse = {
            int(history["nurse_idx"]): history for history in payload["nurse_history"]
        }
        request_nurses = _shift_off_request_nurses(payload["shift_off_requests"])
        self.nurse_indices = list(range(len(nurses)))
        self.total_days = int(payload["num_weeks"]) * 7
        nurse_soft_keys: list[NurseSoftKey] = []
        self.nurse_soft_facts = []
        for nurse_idx, nurse in enumerate(nurses):
            contract = payload["contracts"][int(nurse["contract_idx"])]
            history = history_by_nurse[nurse_idx]
            key: NurseSoftKey = (
                nurse_idx,
                self.total_days,
                int(contract["min_assignments"]),
                int(contract["max_assignments"]),
                int(contract["min_consecutive_working"]),
                int(contract["max_consecutive_working"]),
                int(contract["min_consecutive_off"]),
                int(contract["max_consecutive_off"]),
                int(contract["max_working_weekends"]),
                bool(contract["complete_weekends"]),
                (
                    None
                    if history["last_shift_type_idx"] is None
                    else int(history["last_shift_type_idx"])
                ),
                int(history["num_assignments"]),
                int(history["num_working_weekends"]),
                int(history["num_consecutive_working"]),
                int(history["num_consecutive_off"]),
            )
            nurse_soft_keys.append(key)
            self.nurse_soft_facts.append(NurseSoftFact(key))

        self.nurse_shift_type_facts = []
        shift_type_run_keys: list[list[ShiftTypeRunKey]] = []
        for shift_type_idx, shift_type in enumerate(payload["shift_types"]):
            keys_for_shift_type: list[ShiftTypeRunKey] = []
            for nurse_idx in range(len(nurses)):
                history = history_by_nurse[nurse_idx]
                key = (
                    nurse_idx,
                    shift_type_idx,
                    self.total_days,
                    int(shift_type["min_consecutive"]),
                    int(shift_type["max_consecutive"]),
                    (
                        None
                        if history["last_shift_type_idx"] is None
                        else int(history["last_shift_type_idx"])
                    ),
                    int(history["num_consecutive_assignments"]),
                )
                keys_for_shift_type.append(key)
                self.nurse_shift_type_facts.append(NurseShiftTypeFact(key))
            shift_type_run_keys.append(keys_for_shift_type)

        self.shifts = []
        for shift_id, shift in enumerate(payload["shifts"]):
            shift_type_idx = int(shift["shift_type_idx"])
            skill_idx = int(shift["skill_idx"])
            global_day = int(shift["week"]) * 7 + int(shift["day"])
            self.shifts.append(
                NrpShift(
                    shift_id=shift_id,
                    week=int(shift["week"]),
                    day=int(shift["day"]),
                    shift_type_idx=shift_type_idx,
                    skill_idx=skill_idx,
                    is_minimum=bool(shift["is_minimum"]),
                    nurse_has_skill=[
                        skill_idx in [int(skill) for skill in nurse["skills"]]
                        for nurse in nurses
                    ],
                    history_allows=[
                        _successor_allowed(
                            history_by_nurse[nurse_idx]["last_shift_type_idx"],
                            shift_type_idx,
                            forbidden_successors,
                        )
                        for nurse_idx in range(len(nurses))
                    ],
                    forbidden_predecessors=[
                        int(preceding)
                        for preceding, successors in forbidden_successors.items()
                        if shift_type_idx in successors
                    ],
                    shift_off_request_nurses=request_nurses.get(
                        (global_day, shift_type_idx), []
                    )
                    + request_nurses.get((global_day, _ANY_SHIFT), []),
                    nurse_soft_keys=nurse_soft_keys,
                    shift_type_run_keys=shift_type_run_keys[shift_type_idx],
                    nearby_shift_indices=list(range(len(payload["shifts"]))),
                )
            )
        self.score = None


def solve_with_solverforge_py(instance: Instance, time_limit: int) -> SolverResult:
    instance_json = serialize_instance(instance)
    witness = make_fair_start_witness(
        benchmark_name="employee-scheduling",
        solver="solverforge-py",
        planning_state="unassigned_scalar_variables",
        solver_input=instance_json,
    )
    payload = json.loads(instance_json)
    plan = NrpPythonPlan(payload)
    config = _solver_config(time_limit)

    emit_fair_start_witness(witness)
    solved = Solver.solve(plan, config)
    fresh_score = Solver.analyze(solved)
    reported_cost = _soft_cost(solved.score)
    fresh_cost = _soft_cost(fresh_score)

    weekly: list[list[Assignment]] = [[] for _ in range(int(payload["num_weeks"]))]
    for shift in solved.shifts:
        if shift.nurse_idx is None:
            continue
        weekly[int(shift.week)].append(
            Assignment(
                nurse=payload["nurse_names"][int(shift.nurse_idx)],
                day=DAYS[int(shift.day)],
                shiftType=payload["shift_type_names"][int(shift.shift_type_idx)],
                skill=payload["skill_names"][int(shift.skill_idx)],
            )
        )
    return solver_result(
        Solution(
            assignments=weekly,
            reported_cost=reported_cost,
            fresh_cost=fresh_cost,
            score_delta=(
                reported_cost - fresh_cost
                if reported_cost is not None and fresh_cost is not None
                else None
            ),
            score_drift=(
                reported_cost != fresh_cost
                if reported_cost is not None and fresh_cost is not None
                else None
            ),
            reported_score=str(solved.score),
            fresh_score=str(fresh_score),
            solver_metadata={
                "solverforge_py_score": solved.score,
                "solverforge_py_fresh_score": fresh_score,
                "model_scope": "hard feasibility plus INRC-II soft constraints",
            },
        ),
        witness,
    )


_ANY_SHIFT = 2**64 - 1


def _soft_cost(score: Any) -> int | None:
    if not isinstance(score, dict):
        return None
    levels = score.get("levels")
    if not isinstance(levels, list) or len(levels) < 2:
        return None
    return -int(levels[1])


def _forbidden_successors(
    forbidden: list[dict[str, Any]],
) -> dict[int, set[int]]:
    return {
        int(item["preceding"]): {int(value) for value in item["succeeding"]}
        for item in forbidden
    }


def _successor_allowed(
    previous: int | None,
    current: int,
    forbidden_successors: dict[int, set[int]],
) -> bool:
    if previous is None:
        return True
    return current not in forbidden_successors.get(int(previous), set())


def _shift_off_request_nurses(
    requests: list[dict[str, Any]],
) -> dict[tuple[int, int], list[int]]:
    by_day_shift: dict[tuple[int, int], list[int]] = {}
    for request in requests:
        key = (int(request["global_day"]), int(request["shift_type_idx"]))
        by_day_shift.setdefault(key, []).append(int(request["nurse_idx"]))
    return by_day_shift


def _solver_config(time_limit: int) -> dict[str, Any]:
    return solver_config_for_time_limit(_SOLVER_CONFIG_PATH, time_limit)
