use solverforge::prelude::*;

use crate::domain::{NrpPlan, NrpShift, NurseIndex, NurseShiftTypeIndex};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
struct AssignmentBoundsKey {
    nurse_idx: usize,
    min_assignments: i64,
    max_assignments: i64,
    history_assignments: i64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
struct NurseRunBoundsKey {
    nurse_idx: usize,
    total_days: i64,
    min_consecutive_working: i64,
    max_consecutive_working: i64,
    min_consecutive_off: i64,
    max_consecutive_off: i64,
    history_last_shift_type_idx: Option<usize>,
    history_consecutive_working: i64,
    history_consecutive_off: i64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
struct ShiftTypeRunBoundsKey {
    nurse_idx: usize,
    shift_type_idx: usize,
    total_days: i64,
    min_consecutive: i64,
    max_consecutive: i64,
    history_last_shift_type_idx: Option<usize>,
    history_consecutive_assignments: i64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
struct WorkingWeekendKey {
    nurse_idx: usize,
    max_working_weekends: i64,
    history_working_weekends: i64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
struct CompleteWeekendKey {
    nurse_idx: usize,
    week: usize,
    complete_weekends: bool,
}

pub fn define_constraints() -> impl ConstraintSet<NrpPlan, HardSoftScore> {
    let minimum_coverage = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_none() && shift.is_minimum)
        .penalize(HardSoftScore::of(1_000, 0))
        .named("minimumCoverage");

    let optimal_coverage = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_none() && !shift.is_minimum)
        .penalize(HardSoftScore::of(0, 30))
        .named("optimalCoverage");

    let shift_off_requests = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
        .penalize_with(shift_off_request_penalty as fn(&NrpShift) -> HardSoftScore)
        .named("shiftOffRequests");

    let single_assignment_per_day = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
        .join((
            ConstraintFactory::<NrpPlan, HardSoftScore>::new().for_each(NrpPlan::shifts()),
            joiner::equal_bi(
                |left: &NrpShift| left.nurse_idx,
                |right: &NrpShift| right.nurse_idx,
            ),
        ))
        .filter(|left: &NrpShift, right: &NrpShift| {
            left.id < right.id
                && left.week == right.week
                && left.day == right.day
                && left.nurse_idx == right.nurse_idx
        })
        .penalize_hard()
        .named("singleAssignmentPerDay");

    let required_skill = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
        .join((
            ConstraintFactory::<NrpPlan, HardSoftScore>::new().for_each(NrpPlan::nurse_indices()),
            joiner::equal_bi(
                |shift: &NrpShift| shift.nurse_idx,
                |nurse: &NurseIndex| Some(nurse.id),
            ),
        ))
        .filter(|shift: &NrpShift, nurse: &NurseIndex| !nurse.skills.contains(&shift.skill_idx))
        .penalize_hard()
        .named("requiredSkill");

    let initial_forbidden_succession = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some() && shift.week == 0 && shift.day == 0)
        .join((
            ConstraintFactory::<NrpPlan, HardSoftScore>::new().for_each(NrpPlan::nurse_indices()),
            joiner::equal_bi(
                |shift: &NrpShift| shift.nurse_idx,
                |nurse: &NurseIndex| Some(nurse.id),
            ),
        ))
        .filter(|shift: &NrpShift, nurse: &NurseIndex| {
            nurse
                .last_shift_type_idx
                .is_some_and(|previous| shift.forbidden_predecessors.contains(&previous))
        })
        .penalize_hard()
        .named("initialForbiddenSuccession");

    let adjacent_forbidden_succession = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
        .join((
            ConstraintFactory::<NrpPlan, HardSoftScore>::new().for_each(NrpPlan::shifts()),
            joiner::equal_bi(
                |left: &NrpShift| left.nurse_idx,
                |right: &NrpShift| right.nurse_idx,
            ),
        ))
        .filter(|left: &NrpShift, right: &NrpShift| {
            if left.id >= right.id {
                return false;
            }
            let left_day = left.week * 7 + left.day;
            let right_day = right.week * 7 + right.day;
            if left_day + 1 == right_day {
                right.forbidden_predecessors.contains(&left.shift_type_idx)
            } else if right_day + 1 == left_day {
                left.forbidden_predecessors.contains(&right.shift_type_idx)
            } else {
                false
            }
        })
        .penalize_hard()
        .named("adjacentForbiddenSuccession");

    let total_assignment_bounds = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
        .group_by(
            assignment_bounds_key_from_shift as fn(&NrpShift) -> AssignmentBoundsKey,
            consecutive_runs(|shift: &NrpShift| shift.global_day() as i64),
        )
        .complement(
            NrpPlan::nurse_indices(),
            assignment_bounds_key_from_nurse as fn(&NurseIndex) -> AssignmentBoundsKey,
            |_nurse: &NurseIndex| Runs::default(),
        )
        .penalize_with(
            total_assignment_bounds_penalty as fn(&AssignmentBoundsKey, &Runs) -> HardSoftScore,
        )
        .named("totalAssignmentBounds");

    let consecutive_work_bounds = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
        .group_by(
            nurse_run_bounds_key_from_shift as fn(&NrpShift) -> NurseRunBoundsKey,
            consecutive_runs(|shift: &NrpShift| shift.global_day() as i64),
        )
        .complement(
            NrpPlan::nurse_indices(),
            nurse_run_bounds_key_from_nurse as fn(&NurseIndex) -> NurseRunBoundsKey,
            |_nurse: &NurseIndex| Runs::default(),
        )
        .penalize_with(
            consecutive_work_bounds_penalty as fn(&NurseRunBoundsKey, &Runs) -> HardSoftScore,
        )
        .named("consecutiveWorkBounds");

    let consecutive_off_bounds = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
        .group_by(
            nurse_run_bounds_key_from_shift as fn(&NrpShift) -> NurseRunBoundsKey,
            consecutive_runs(|shift: &NrpShift| shift.global_day() as i64),
        )
        .complement(
            NrpPlan::nurse_indices(),
            nurse_run_bounds_key_from_nurse as fn(&NurseIndex) -> NurseRunBoundsKey,
            |_nurse: &NurseIndex| Runs::default(),
        )
        .penalize_with(
            consecutive_off_bounds_penalty as fn(&NurseRunBoundsKey, &Runs) -> HardSoftScore,
        )
        .named("consecutiveOffBounds");

    let consecutive_shift_type_bounds = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
        .group_by(
            shift_type_run_bounds_key_from_shift as fn(&NrpShift) -> ShiftTypeRunBoundsKey,
            consecutive_runs(|shift: &NrpShift| shift.global_day() as i64),
        )
        .complement(
            NrpPlan::nurse_shift_type_indices(),
            shift_type_run_bounds_key_from_fact
                as fn(&NurseShiftTypeIndex) -> ShiftTypeRunBoundsKey,
            |_fact: &NurseShiftTypeIndex| Runs::default(),
        )
        .penalize_with(
            consecutive_shift_type_bounds_penalty
                as fn(&ShiftTypeRunBoundsKey, &Runs) -> HardSoftScore,
        )
        .named("consecutiveShiftTypeBounds");

    let working_weekends = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some() && shift.day >= 5)
        .group_by(
            working_weekend_key_from_shift as fn(&NrpShift) -> WorkingWeekendKey,
            consecutive_runs(|shift: &NrpShift| shift.week as i64),
        )
        .complement(
            NrpPlan::nurse_indices(),
            working_weekend_key_from_nurse as fn(&NurseIndex) -> WorkingWeekendKey,
            |_nurse: &NurseIndex| Runs::default(),
        )
        .penalize_with(working_weekends_penalty as fn(&WorkingWeekendKey, &Runs) -> HardSoftScore)
        .named("workingWeekends");

    let complete_weekends = ConstraintFactory::<NrpPlan, HardSoftScore>::new()
        .for_each(NrpPlan::shifts())
        .filter(|shift: &NrpShift| shift.nurse_idx.is_some() && shift.day >= 5)
        .group_by(
            complete_weekend_key_from_shift as fn(&NrpShift) -> CompleteWeekendKey,
            consecutive_runs(|shift: &NrpShift| shift.day as i64),
        )
        .penalize_with(complete_weekends_penalty as fn(&CompleteWeekendKey, &Runs) -> HardSoftScore)
        .named("completeWeekends");

    (
        minimum_coverage,
        optimal_coverage,
        shift_off_requests,
        single_assignment_per_day,
        required_skill,
        initial_forbidden_succession,
        adjacent_forbidden_succession,
        total_assignment_bounds,
        consecutive_work_bounds,
        consecutive_off_bounds,
        consecutive_shift_type_bounds,
        working_weekends,
        complete_weekends,
    )
}

fn shift_off_request_penalty(shift: &NrpShift) -> HardSoftScore {
    let Some(nurse_idx) = shift.nurse_idx else {
        return HardSoftScore::ZERO;
    };
    let request_count = shift
        .shift_off_request_nurses
        .iter()
        .filter(|request_nurse| **request_nurse == nurse_idx)
        .count() as i64;
    HardSoftScore::of_soft(request_count * 10)
}

fn assignment_bounds_key_from_shift(shift: &NrpShift) -> AssignmentBoundsKey {
    let nurse_idx = shift.nurse_idx.unwrap_or(0);
    let data = shift.problem_data();
    let nurse = &data.nurses[nurse_idx];
    let contract = &data.contracts[nurse.contract_idx];
    let history = &data.nurse_history[nurse_idx];
    AssignmentBoundsKey {
        nurse_idx,
        min_assignments: contract.min_assignments,
        max_assignments: contract.max_assignments,
        history_assignments: history.num_assignments,
    }
}

fn assignment_bounds_key_from_nurse(nurse: &NurseIndex) -> AssignmentBoundsKey {
    AssignmentBoundsKey {
        nurse_idx: nurse.id,
        min_assignments: nurse.min_assignments,
        max_assignments: nurse.max_assignments,
        history_assignments: nurse.history_assignments,
    }
}

fn nurse_run_bounds_key_from_shift(shift: &NrpShift) -> NurseRunBoundsKey {
    let nurse_idx = shift.nurse_idx.unwrap_or(0);
    let data = shift.problem_data();
    let nurse = &data.nurses[nurse_idx];
    let contract = &data.contracts[nurse.contract_idx];
    let history = &data.nurse_history[nurse_idx];
    NurseRunBoundsKey {
        nurse_idx,
        total_days: data.total_days() as i64,
        min_consecutive_working: contract.min_consecutive_working,
        max_consecutive_working: contract.max_consecutive_working,
        min_consecutive_off: contract.min_consecutive_off,
        max_consecutive_off: contract.max_consecutive_off,
        history_last_shift_type_idx: history.last_shift_type_idx,
        history_consecutive_working: history.num_consecutive_working,
        history_consecutive_off: history.num_consecutive_off,
    }
}

fn nurse_run_bounds_key_from_nurse(nurse: &NurseIndex) -> NurseRunBoundsKey {
    NurseRunBoundsKey {
        nurse_idx: nurse.id,
        total_days: nurse.total_days,
        min_consecutive_working: nurse.min_consecutive_working,
        max_consecutive_working: nurse.max_consecutive_working,
        min_consecutive_off: nurse.min_consecutive_off,
        max_consecutive_off: nurse.max_consecutive_off,
        history_last_shift_type_idx: nurse.last_shift_type_idx,
        history_consecutive_working: nurse.history_consecutive_working,
        history_consecutive_off: nurse.history_consecutive_off,
    }
}

fn shift_type_run_bounds_key_from_shift(shift: &NrpShift) -> ShiftTypeRunBoundsKey {
    let nurse_idx = shift.nurse_idx.unwrap_or(0);
    let data = shift.problem_data();
    let shift_type = &data.shift_types[shift.shift_type_idx];
    let history = &data.nurse_history[nurse_idx];
    ShiftTypeRunBoundsKey {
        nurse_idx,
        shift_type_idx: shift.shift_type_idx,
        total_days: data.total_days() as i64,
        min_consecutive: shift_type.min_consecutive,
        max_consecutive: shift_type.max_consecutive,
        history_last_shift_type_idx: history.last_shift_type_idx,
        history_consecutive_assignments: history.num_consecutive_assignments,
    }
}

fn shift_type_run_bounds_key_from_fact(fact: &NurseShiftTypeIndex) -> ShiftTypeRunBoundsKey {
    ShiftTypeRunBoundsKey {
        nurse_idx: fact.nurse_idx,
        shift_type_idx: fact.shift_type_idx,
        total_days: fact.total_days,
        min_consecutive: fact.min_consecutive,
        max_consecutive: fact.max_consecutive,
        history_last_shift_type_idx: fact.history_last_shift_type_idx,
        history_consecutive_assignments: fact.history_consecutive_assignments,
    }
}

fn working_weekend_key_from_shift(shift: &NrpShift) -> WorkingWeekendKey {
    let nurse_idx = shift.nurse_idx.unwrap_or(0);
    let data = shift.problem_data();
    let nurse = &data.nurses[nurse_idx];
    let contract = &data.contracts[nurse.contract_idx];
    let history = &data.nurse_history[nurse_idx];
    WorkingWeekendKey {
        nurse_idx,
        max_working_weekends: contract.max_working_weekends,
        history_working_weekends: history.num_working_weekends,
    }
}

fn working_weekend_key_from_nurse(nurse: &NurseIndex) -> WorkingWeekendKey {
    WorkingWeekendKey {
        nurse_idx: nurse.id,
        max_working_weekends: nurse.max_working_weekends,
        history_working_weekends: nurse.history_working_weekends,
    }
}

fn complete_weekend_key_from_shift(shift: &NrpShift) -> CompleteWeekendKey {
    let nurse_idx = shift.nurse_idx.unwrap_or(0);
    let data = shift.problem_data();
    let nurse = &data.nurses[nurse_idx];
    let contract = &data.contracts[nurse.contract_idx];
    CompleteWeekendKey {
        nurse_idx,
        week: shift.week,
        complete_weekends: contract.complete_weekends,
    }
}

fn total_assignment_bounds_penalty(key: &AssignmentBoundsKey, runs: &Runs) -> HardSoftScore {
    let total_assigned = runs.point_count() as i64 + key.history_assignments;
    let cost = if total_assigned < key.min_assignments {
        20 * (key.min_assignments - total_assigned)
    } else if total_assigned > key.max_assignments {
        20 * (total_assigned - key.max_assignments)
    } else {
        0
    };
    HardSoftScore::of_soft(cost)
}

fn consecutive_work_bounds_penalty(key: &NurseRunBoundsKey, runs: &Runs) -> HardSoftScore {
    let mut cost = 0;
    let history_extends_work = key.history_last_shift_type_idx.is_some();
    let mut history_consumed = !history_extends_work;

    for run in runs.runs() {
        if !history_consumed && run.start() > 0 {
            cost += closed_bounds_cost(
                key.history_consecutive_working,
                key.min_consecutive_working,
                key.max_consecutive_working,
                30,
            );
            history_consumed = true;
        }

        let mut length = run.point_count() as i64;
        if !history_consumed && run.start() == 0 {
            length += key.history_consecutive_working;
            history_consumed = true;
        }

        if run.end() + 1 < key.total_days {
            cost += closed_bounds_cost(
                length,
                key.min_consecutive_working,
                key.max_consecutive_working,
                30,
            );
        } else {
            cost += max_bound_cost(length, key.max_consecutive_working, 30);
        }
    }

    if runs.is_empty() && history_extends_work {
        cost += closed_bounds_cost(
            key.history_consecutive_working,
            key.min_consecutive_working,
            key.max_consecutive_working,
            30,
        );
    }

    HardSoftScore::of_soft(cost)
}

fn consecutive_off_bounds_penalty(key: &NurseRunBoundsKey, runs: &Runs) -> HardSoftScore {
    let mut cost = 0;
    let mut cursor = 0;
    let mut off_length = if key.history_last_shift_type_idx.is_none() {
        key.history_consecutive_off
    } else {
        0
    };

    for run in runs.runs() {
        off_length += run.start().saturating_sub(cursor);
        cost += closed_bounds_cost(
            off_length,
            key.min_consecutive_off,
            key.max_consecutive_off,
            30,
        );
        off_length = 0;
        cursor = run.end() + 1;
    }

    if cursor < key.total_days {
        off_length += key.total_days - cursor;
    }
    cost += max_bound_cost(off_length, key.max_consecutive_off, 30);

    HardSoftScore::of_soft(cost)
}

fn consecutive_shift_type_bounds_penalty(
    key: &ShiftTypeRunBoundsKey,
    runs: &Runs,
) -> HardSoftScore {
    let mut cost = 0;
    let history_extends_shift = key.history_last_shift_type_idx == Some(key.shift_type_idx);
    let mut history_consumed = !history_extends_shift;

    for run in runs.runs() {
        if !history_consumed && run.start() > 0 {
            cost += closed_bounds_cost(
                key.history_consecutive_assignments,
                key.min_consecutive,
                key.max_consecutive,
                15,
            );
            history_consumed = true;
        }

        let mut length = run.point_count() as i64;
        if !history_consumed && run.start() == 0 {
            length += key.history_consecutive_assignments;
            history_consumed = true;
        }

        if run.end() + 1 < key.total_days {
            cost += closed_bounds_cost(length, key.min_consecutive, key.max_consecutive, 15);
        } else {
            cost += max_bound_cost(length, key.max_consecutive, 15);
        }
    }

    if runs.is_empty() && history_extends_shift {
        cost += closed_bounds_cost(
            key.history_consecutive_assignments,
            key.min_consecutive,
            key.max_consecutive,
            15,
        );
    }

    HardSoftScore::of_soft(cost)
}

fn working_weekends_penalty(key: &WorkingWeekendKey, runs: &Runs) -> HardSoftScore {
    let working_weekends = key.history_working_weekends + runs.point_count() as i64;
    HardSoftScore::of_soft(max_bound_cost(
        working_weekends,
        key.max_working_weekends,
        30,
    ))
}

fn complete_weekends_penalty(key: &CompleteWeekendKey, runs: &Runs) -> HardSoftScore {
    let cost = if key.complete_weekends && runs.point_count() == 1 {
        30
    } else {
        0
    };
    HardSoftScore::of_soft(cost)
}

fn closed_bounds_cost(length: i64, min: i64, max: i64, weight: i64) -> i64 {
    if length == 0 {
        return 0;
    }
    let mut cost = 0;
    if length < min {
        cost += weight * (min - length);
    }
    if length > max {
        cost += weight * (length - max);
    }
    cost
}

fn max_bound_cost(length: i64, max: i64, weight: i64) -> i64 {
    if length > max {
        weight * (length - max)
    } else {
        0
    }
}
