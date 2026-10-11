from __future__ import annotations

import json
import math
from typing import Any

import highspy
import numpy as np

from employee_scheduling_bench.domain.models import Assignment, Instance, Solution
from employee_scheduling_bench.solver.instance_json import serialize_instance
from employee_scheduling_bench.validation import validate
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import (
    NoSolutionFoundError,
    SolverExecutionError,
    SolverResult,
)

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_REQUEST_WEIGHT = 10
_ASSIGNMENT_WEIGHT = 20
_UNCOVERED_WEIGHT = 30


def _status_name(h: highspy.Highs) -> str:
    return str(h.modelStatusToString(h.getModelStatus()))


def _native_fields(h: highspy.Highs, num_cols: int, num_rows: int) -> dict[str, Any]:
    info = h.getInfo()
    gap = float(info.mip_gap)
    return {
        "native_solver_status": _status_name(h),
        "highs_mip_gap": gap if math.isfinite(gap) else None,
        "highs_mip_node_count": int(info.mip_node_count),
        "highs_model_columns": num_cols,
        "highs_model_rows": num_rows,
    }


class _MilpBuilder:
    """Row/col accumulator over the highspy bulk matrix API."""

    def __init__(self) -> None:
        self.h = highspy.Highs()
        self.h.setOptionValue("output_flag", False)
        self.h.setOptionValue("log_to_console", False)
        self.h.setOptionValue("threads", 1)
        self.h.setOptionValue("random_seed", 1)
        self.col_cost: list[float] = []
        self.col_lower: list[float] = []
        self.col_upper: list[float] = []
        self.integer_cols: list[int] = []
        self.row_lower: list[float] = []
        self.row_upper: list[float] = []
        self.row_starts: list[int] = []
        self.row_indices: list[int] = []
        self.row_values: list[float] = []

    def add_col(
        self, lower: float, upper: float, cost: float = 0.0, *, integer: bool = False
    ) -> int:
        index = len(self.col_cost)
        self.col_cost.append(cost)
        self.col_lower.append(lower)
        self.col_upper.append(upper)
        if integer:
            self.integer_cols.append(index)
        return index

    def add_row(
        self, entries: list[tuple[int, float]], lower: float, upper: float
    ) -> None:
        self.row_starts.append(len(self.row_indices))
        self.row_lower.append(lower)
        self.row_upper.append(upper)
        for col, coef in entries:
            self.row_indices.append(col)
            self.row_values.append(coef)

    def finish(self) -> tuple[highspy.Highs, int, int]:
        num_col = len(self.col_cost)
        num_row = len(self.row_lower)
        self.h.addCols(
            num_col,
            np.array(self.col_cost, dtype=np.float64),
            np.array(self.col_lower, dtype=np.float64),
            np.array(self.col_upper, dtype=np.float64),
            0,
            np.array([], dtype=np.int32),
            np.array([], dtype=np.int32),
            np.array([], dtype=np.float64),
        )
        self.h.addRows(
            num_row,
            np.array(self.row_lower, dtype=np.float64),
            np.array(self.row_upper, dtype=np.float64),
            len(self.row_indices),
            np.array(self.row_starts, dtype=np.int32),
            np.array(self.row_indices, dtype=np.int32),
            np.array(self.row_values, dtype=np.float64),
        )
        if self.integer_cols:
            # Integrality only on the assignment decision columns. Every other
            # column is either equality-pinned to them (work/type indicators,
            # complements) or a minimized envelope whose incumbent value is a
            # nonnegative integer by construction, so declaring all columns
            # integer would only multiply branch-and-bound variables.
            integrality = np.full(
                len(self.integer_cols), highspy.HighsVarType.kInteger, dtype=np.uint8
            )
            self.h.changeColsIntegrality(
                len(self.integer_cols),
                np.array(self.integer_cols, dtype=np.int32),
                integrality,
            )
        return self.h, num_col, num_row


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


def _add_run_length_costs(
    builder: _MilpBuilder,
    active_cols: list[int],
    history_active: bool,
    history_length: int,
    min_length: int,
    max_length: int,
    weight: int,
) -> None:
    """
    MILP mirror of the CP-SAT run-length block: an integer run-length variable
    per day pinned by exact transition rows, a penalty variable per run closure
    charged ClosedBoundsCost(closing run length), an end-of-horizon penalty
    charged MaxBoundCost(open run length), and the constant history closure
    cost charged on a complement literal of day 0. Weights and bounds match the
    CP-SAT adapter exactly; the model minimizes, so lower-bounded penalty
    variables sit at max(under, over, 0).
    """
    if not active_cols:
        return

    n = len(active_cols)
    max_possible_length = n + max(0, history_length)
    max_closed_cost = 0
    max_end_cost = 0
    for length in range(max_possible_length + 1):
        max_closed_cost = max(
            max_closed_cost,
            max(0, (min_length - length) * weight, (length - max_length) * weight),
        )
        max_end_cost = max(max_end_cost, _max_bound_cost(length, max_length, weight))

    big_m = float(max_possible_length + 1)
    release_m = float(weight * max_possible_length)
    inf = highspy.kHighsInf
    run_cols: list[int] = []

    # Day 0: r_0 = active_length * a_0 (two exact rows). When the history run
    # is active, its closure cost rides a complement literal of day 0: the
    # CP-SAT adapter charges ClosedBoundsCost(history_length) on
    # active_by_day[0].Not(), i.e. exactly when day 0 is inactive and the
    # history run closes at the horizon boundary.
    active_length = history_length + 1 if history_active else 1
    first = active_cols[0]
    run_cols.append(builder.add_col(0.0, float(max_possible_length)))
    builder.add_row([(run_cols[0], -1.0), (first, float(active_length))], 0.0, 0.0)
    builder.add_row([(run_cols[0], 1.0), (first, -float(active_length))], 0.0, 0.0)
    history_cost = 0
    if history_active and history_length > 0:
        history_cost = _closed_bounds_cost(
            history_length, min_length, max_length, weight
        )
    if history_cost:
        complement = builder.add_col(0.0, 1.0, float(history_cost))
        builder.add_row([(complement, 1.0), (first, 1.0)], 1.0, 1.0)

    # Days 1..n-1: exact run-length transitions. For every big-M row the
    # literal coefficient and the bound shift follow LHS - M*z >= RHS - M, so
    # z=1 enforces and z=0 releases. Together the rows pin r_d = 0 when
    # inactive, r_d = r_{d-1} + 1 when continuing, and r_d = 1 at run starts.
    for day in range(1, n):
        active = active_cols[day]
        previous_active = active_cols[day - 1]
        run = builder.add_col(0.0, float(max_possible_length))
        run_cols.append(run)
        # Inactive day pins its run length to zero: r_d <= max_len * a_d.
        builder.add_row([(run, 1.0), (active, -float(max_possible_length))], -inf, 0.0)
        # Continuation upper: r_d <= r_{d-1} + 1 when both days work
        # (r_d - r_{d-1} + M*a_d + M*a_{d-1} <= 1 + 2M).
        builder.add_row(
            [
                (run, 1.0),
                (run_cols[day - 1], -1.0),
                (active, big_m),
                (previous_active, big_m),
            ],
            -inf,
            1.0 + 2.0 * big_m,
        )
        # Continuation lower: r_d >= r_{d-1} + 1 when both days work.
        builder.add_row(
            [
                (run, 1.0),
                (run_cols[day - 1], -1.0),
                (active, -big_m),
                (previous_active, -big_m),
            ],
            1.0 - 2.0 * big_m,
            inf,
        )
        # Start lower: r_d >= 1 when day d works and d-1 does not
        # (r_d - M*a_d + M*a_{d-1} >= 1 - M).
        builder.add_row(
            [(run, 1.0), (active, -big_m), (previous_active, big_m)],
            1.0 - big_m,
            inf,
        )
        # Start upper cap: r_d <= 1 when day d works and d-1 does not
        # (r_d + M*a_d - M*a_{d-1} <= 1 + M); released (vacuous) otherwise, so
        # it never conflicts with exact continuations.
        builder.add_row(
            [(run, 1.0), (active, big_m), (previous_active, -big_m)],
            -inf,
            1.0 + big_m,
        )

    # Closure penalties: close_d is exactly (a_{d-1} worked, day d off), and the
    # penalty carries ClosedBoundsCost over the run that ended before day d.
    for day in range(1, n):
        active = active_cols[day]
        previous_active = active_cols[day - 1]
        close = builder.add_col(0.0, 1.0)
        builder.add_row([(close, 1.0), (previous_active, -1.0)], -inf, 0.0)
        builder.add_row([(close, 1.0), (active, 1.0)], -inf, 1.0)
        builder.add_row(
            [(close, 1.0), (previous_active, -1.0), (active, 1.0)], 0.0, inf
        )
        penalty = builder.add_col(0.0, float(max_closed_cost), 1.0)
        # Over-maximum release: P >= w*(r - maxL) when close. LHS - M*z >=
        # RHS - M gives the -M coefficient and the shifted bound.
        builder.add_row(
            [
                (penalty, 1.0),
                (run_cols[day - 1], -float(weight)),
                (close, -release_m),
            ],
            float(-max_length * weight) - release_m,
            inf,
        )
        # Under-minimum release: P >= w*(minL - r) when close, same shift.
        builder.add_row(
            [
                (penalty, 1.0),
                (run_cols[day - 1], float(weight)),
                (close, -release_m),
            ],
            float(min_length * weight) - release_m,
            inf,
        )

    # End-of-horizon penalty on the open final run: over-maximum only, charged
    # only when the last day is active, mirroring the CP-SAT end row. The
    # enforcement literal is the last-day activation itself, so it releases via
    # the same LHS - M*z >= RHS - M shift.
    end_penalty = builder.add_col(0.0, float(max_end_cost), 1.0)
    last = active_cols[-1]
    builder.add_row(
        [
            (end_penalty, 1.0),
            (run_cols[-1], -float(weight)),
            (last, -release_m),
        ],
        float(-max_length * weight) - release_m,
        inf,
    )
    builder.add_row([(end_penalty, 1.0), (last, -float(max_end_cost))], -inf, 0.0)


class _PayloadReader:
    """Read the instance_json payload shape the C++ adapters parse."""

    def __init__(self, text: str) -> None:
        data = json.loads(text)
        self.nurses: list[dict[str, Any]] = data["nurses"]
        self.contracts: list[dict[str, Any]] = data["contracts"]
        self.shift_types: list[dict[str, Any]] = data["shift_types"]
        self.forbidden: dict[int, set[int]] = {}
        for entry in data["forbidden"]:
            self.forbidden.setdefault(int(entry["preceding"]), set()).update(
                int(s) for s in entry["succeeding"]
            )
        self.requests: list[tuple[int, int, int]] = [
            (int(r["nurse_idx"]), int(r["global_day"]), int(r["shift_type_idx"]))
            for r in data["shift_off_requests"]
        ]
        self.histories: dict[int, dict[str, int]] = {}
        for raw in data["nurse_history"]:
            last = raw["last_shift_type_idx"]
            self.histories[int(raw["nurse_idx"])] = {
                "num_assignments": int(raw["num_assignments"]),
                "num_working_weekends": int(raw["num_working_weekends"]),
                "last_shift_type_idx": (-1 if last is None else int(last)),
                "num_consecutive_assignments": int(raw["num_consecutive_assignments"]),
                "num_consecutive_working": int(raw["num_consecutive_working"]),
                "num_consecutive_off": int(raw["num_consecutive_off"]),
            }
        self.shifts: list[dict[str, int]] = data["shifts"]
        self.num_weeks: int = int(data["num_weeks"])
        self.skill_names: list[str] = data["skill_names"]
        self.shift_type_names: list[str] = data["shift_type_names"]
        self.nurse_names: list[str] = data["nurse_names"]

    def is_forbidden(self, preceding: int, succeeding: int) -> bool:
        if preceding < 0:
            return False
        return succeeding in self.forbidden.get(preceding, ())


def solve_with_highs(instance: Instance, time_limit: int) -> SolverResult:
    """
    HiGHS (highspy) employee-rostering adapter: the mainline C++ HiGHS core
    through its published Python wheel. The MILP mirrors the OR-Tools CP-SAT
    adapter's model (coverage windows, forbidden successions, contract
    bounds, run-length costs with history, complete weekends, working-weekend
    caps, shift-off requests) with identical weights, from a blank schedule.
    """
    witness = make_fair_start_witness(
        benchmark_name="employee-scheduling",
        solver="highs",
        planning_state="external_solver_model",
        solver_input=serialize_instance(instance),
    )
    emit_fair_start_witness(witness)

    payload = _PayloadReader(serialize_instance(instance))
    num_nurses = len(payload.nurses)
    total_days = payload.num_weeks * 7
    any_shift = 2**64 - 1

    builder = _MilpBuilder()
    inf = highspy.kHighsInf

    # Coverage requirements: aggregate shipped shift slots into
    # (week, day, shift type, skill) -> (minimum, optimal).
    coverage: dict[tuple[int, int, int, int], list[int]] = {}
    for shift in payload.shifts:
        key = (
            int(shift["week"]),
            int(shift["day"]),
            int(shift["shift_type_idx"]),
            int(shift["skill_idx"]),
        )
        counts = coverage.setdefault(key, [0, 0])
        counts[1] += 1
        if shift["is_minimum"]:
            counts[0] += 1
    coverage_keys = sorted(coverage)
    for key in coverage_keys:
        if coverage[key][0] < 0 or coverage[key][1] <= 0:
            raise SolverExecutionError("invalid employee coverage requirement")

    # Assignment binaries per (coverage requirement, nurse) where the nurse has
    # the skill and the day-0 succession filter does not exclude the pair.
    assign: dict[tuple[int, int], int] = {}
    for coverage_idx, key in enumerate(coverage_keys):
        week, day, shift_type_idx, skill_idx = key
        global_day = week * 7 + day
        for nurse_idx in range(num_nurses):
            if skill_idx not in payload.nurses[nurse_idx]["skills"]:
                continue
            if global_day == 0 and payload.is_forbidden(
                payload.histories[nurse_idx]["last_shift_type_idx"],
                shift_type_idx,
            ):
                continue
            assign[(coverage_idx, nurse_idx)] = builder.add_col(0.0, 1.0, integer=True)

    def request_count(nurse_idx: int, global_day: int, shift_type_idx: int) -> int:
        return sum(
            1
            for nurse, r_day, r_shift in payload.requests
            if nurse == nurse_idx
            and r_day == global_day
            and (r_shift == any_shift or r_shift == shift_type_idx)
        )

    # Objective terms and per-coverage rows.
    for coverage_idx, key in enumerate(coverage_keys):
        week, day, shift_type_idx, skill_idx = key
        global_day = week * 7 + day
        candidates = [
            assign[(coverage_idx, nurse_idx)]
            for nurse_idx in range(num_nurses)
            if (coverage_idx, nurse_idx) in assign
        ]
        if not candidates:
            raise SolverExecutionError(
                "no nurse can cover a required (day, shift type, skill)"
            )
        builder.add_row(
            [(col, 1.0) for col in candidates],
            float(coverage[key][0]),
            float(coverage[key][1]),
        )
        uncovered = builder.add_col(0.0, float(coverage[key][1]), _UNCOVERED_WEIGHT)
        builder.add_row(
            [(uncovered, 1.0)] + [(col, 1.0) for col in candidates],
            float(coverage[key][1]),
            float(coverage[key][1]),
        )
        for nurse_idx in range(num_nurses):
            col = assign.get((coverage_idx, nurse_idx))
            if col is None:
                continue
            count = request_count(nurse_idx, global_day, shift_type_idx)
            if count:
                builder.col_cost[col] += _REQUEST_WEIGHT * count

    # Per-nurse day/shift-type aggregates: one assignment-column list per
    # (nurse, day) and per (nurse, day, shift type), then equality-summed into
    # binary work / shift-type indicator columns.
    assign_by_nurse_day: list[list[list[int]]] = [
        [[] for _ in range(total_days)] for _ in range(num_nurses)
    ]
    assign_by_nurse_day_type: list[list[list[list[int]]]] = [
        [[[] for _ in range(len(payload.shift_types))] for _ in range(total_days)]
        for _ in range(num_nurses)
    ]
    for (coverage_idx, nurse_idx), col in assign.items():
        week, day, shift_type_idx, _skill = coverage_keys[coverage_idx]
        global_day = week * 7 + day
        assign_by_nurse_day[nurse_idx][global_day].append(col)
        assign_by_nurse_day_type[nurse_idx][global_day][shift_type_idx].append(col)

    work: list[list[int]] = [[0] * total_days for _ in range(num_nurses)]
    type_work: list[list[list[int]]] = [
        [[0] * len(payload.shift_types) for _ in range(total_days)]
        for _ in range(num_nurses)
    ]
    for nurse_idx in range(num_nurses):
        for day in range(total_days):
            group = assign_by_nurse_day[nurse_idx][day]
            work_col = builder.add_col(0.0, 1.0)
            work[nurse_idx][day] = work_col
            builder.add_row([(work_col, 1.0)] + [(c, -1.0) for c in group], 0.0, 0.0)
            for st_idx in range(len(payload.shift_types)):
                type_group = assign_by_nurse_day_type[nurse_idx][day][st_idx]
                tcol = builder.add_col(0.0, 1.0)
                type_work[nurse_idx][day][st_idx] = tcol
                builder.add_row(
                    [(tcol, 1.0)] + [(c, -1.0) for c in type_group], 0.0, 0.0
                )

    # Forbidden successions: type(d, p) and type(d+1, s) cannot both be 1 for
    # every forbidden (preceding, succeeding) pair.
    pairs: list[tuple[int, int]] = sorted(payload.forbidden.items())
    for nurse_idx in range(num_nurses):
        for day in range(total_days - 1):
            for preceding, successors in pairs:
                for succeeding in successors:
                    builder.add_row(
                        [
                            (type_work[nurse_idx][day][preceding], 1.0),
                            (type_work[nurse_idx][day + 1][succeeding], 1.0),
                        ],
                        -inf,
                        1.0,
                    )

    # Contracts, soft with history.
    for nurse_idx in range(num_nurses):
        nurse = payload.nurses[nurse_idx]
        contract = payload.contracts[nurse["contract_idx"]]
        history = payload.histories[nurse_idx]
        mine = [col for (c_idx, n_idx), col in assign.items() if n_idx == nurse_idx]
        total_upper = history["num_assignments"] + total_days
        count_expr = [(col, 1.0) for col in mine]

        under = builder.add_col(0.0, float(total_upper), _ASSIGNMENT_WEIGHT)
        builder.add_row(
            [(under, 1.0)] + [(c, 1.0) for c in mine],
            float(contract["min_assignments"] - history["num_assignments"]),
            inf,
        )
        over = builder.add_col(0.0, float(total_upper), _ASSIGNMENT_WEIGHT)
        builder.add_row(
            [(over, -1.0)] + count_expr,
            -inf,
            float(contract["max_assignments"] - history["num_assignments"]),
        )

        _add_run_length_costs(
            builder,
            work[nurse_idx],
            history["last_shift_type_idx"] >= 0,
            history["num_consecutive_working"],
            contract["min_consecutive_working"],
            contract["max_consecutive_working"],
            30,
        )
        # Mirror the CP-SAT trick of running the same machinery over the
        # complement literal columns.
        off_active = [
            _complement_col(builder, work[nurse_idx][day]) for day in range(total_days)
        ]
        _add_run_length_costs(
            builder,
            off_active,
            history["last_shift_type_idx"] < 0,
            history["num_consecutive_off"],
            contract["min_consecutive_off"],
            contract["max_consecutive_off"],
            30,
        )
        for st_idx in range(len(payload.shift_types)):
            _add_run_length_costs(
                builder,
                [type_work[nurse_idx][day][st_idx] for day in range(total_days)],
                history["last_shift_type_idx"] == st_idx,
                history["num_consecutive_assignments"],
                payload.shift_types[st_idx]["min_consecutive"],
                payload.shift_types[st_idx]["max_consecutive"],
                15,
            )

        # Weekends.
        weekend_max = payload.num_weeks + history["num_working_weekends"]
        weekend_cols: list[int] = []
        for week in range(payload.num_weeks):
            saturday = work[nurse_idx][week * 7 + 5]
            sunday = work[nurse_idx][week * 7 + 6]
            weekend = builder.add_col(0.0, 1.0)
            builder.add_row([(weekend, -1.0), (saturday, 1.0)], -inf, 0.0)
            builder.add_row([(weekend, -1.0), (sunday, 1.0)], -inf, 0.0)
            # Minimization pressure pushes weekend to max(sat, sun); no lower
            # bound rows are needed.
            weekend_cols.append(weekend)
            if contract["complete_weekends"]:
                # incomplete is max(sat - sun, sun - sat) via the two upper
                # release rows; without them it collapses to 0 and never pays.
                incomplete = builder.add_col(0.0, 1.0, 30.0)
                builder.add_row(
                    [(incomplete, -1.0), (saturday, 1.0), (sunday, -1.0)],
                    -inf,
                    0.0,
                )
                builder.add_row(
                    [(incomplete, -1.0), (saturday, -1.0), (sunday, 1.0)],
                    -inf,
                    0.0,
                )
        over_weekends = builder.add_col(0.0, float(weekend_max), 30.0)
        builder.add_row(
            [(over_weekends, -1.0)] + [(c, 1.0) for c in weekend_cols],
            -inf,
            float(contract["max_working_weekends"] - history["num_working_weekends"]),
        )

    h, num_cols, num_rows = builder.finish()
    h.setOptionValue("time_limit", float(max(0.1, time_limit)))
    h.run()
    model_status = h.getModelStatus()
    solution = h.getSolution()
    native_fields = _native_fields(h, num_cols, num_rows)
    if model_status == highspy.HighsModelStatus.kInfeasible:
        raise NoSolutionFoundError(
            "HiGHS proved the rostering model infeasible",
            termination_status="proved_infeasible",
            native_fields=native_fields,
        )
    if model_status != highspy.HighsModelStatus.kOptimal and not solution.value_valid:
        raise NoSolutionFoundError(
            "HiGHS returned no rostering incumbent before the time limit",
            termination_status="no_incumbent",
            native_fields=native_fields,
        )

    values = solution.col_value
    weeks: list[list[Assignment]] = [[] for _ in range(payload.num_weeks)]
    for (coverage_idx, nurse_idx), col in assign.items():
        if values[col] <= 0.5:
            continue
        week, day, shift_type_idx, skill_idx = coverage_keys[coverage_idx]
        weeks[week].append(
            Assignment(
                nurse=payload.nurse_names[nurse_idx],
                day=_DAYS[day],
                shiftType=payload.shift_type_names[shift_type_idx],
                skill=payload.skill_names[skill_idx],
            )
        )

    objective = int(round(h.getObjectiveValue()))
    solution_model = Solution(
        assignments=weeks,
        reported_cost=objective,
        solver_metadata=native_fields,
    )
    fresh = validate(solution=solution_model, instance=instance)
    solution_model.cost = fresh
    solution_model.fresh_cost = fresh
    solution_model.score_delta = (
        solution_model.reported_cost - fresh
        if solution_model.reported_cost is not None
        else None
    )
    solution_model.score_drift = (
        solution_model.reported_cost != fresh
        if solution_model.reported_cost is not None
        else None
    )
    return solver_result(solution_model, witness)


def _complement_col(builder: _MilpBuilder, source: int) -> int:
    complement = builder.add_col(0.0, 1.0)
    # complement == 1 - source, both directions.
    builder.add_row([(complement, 1.0), (source, 1.0)], 1.0, 1.0)
    builder.add_row([(complement, -1.0), (source, -1.0)], -1.0, -1.0)
    return complement
