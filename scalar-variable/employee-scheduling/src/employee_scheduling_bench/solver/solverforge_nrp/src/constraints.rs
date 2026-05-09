use solverforge::prelude::*;

use crate::domain::{NrpPlan, NrpShift, NurseIndex, NurseShiftTypeIndex};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
struct NurseSoftKey {
    nurse_idx: usize,
    total_days: i64,
    min_assignments: i64,
    max_assignments: i64,
    min_consecutive_working: i64,
    max_consecutive_working: i64,
    min_consecutive_off: i64,
    max_consecutive_off: i64,
    max_working_weekends: i64,
    complete_weekends: bool,
    history_last_shift_type_idx: Option<usize>,
    history_assignments: i64,
    history_working_weekends: i64,
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

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
struct AssignedShiftProjection {
    global_day: i64,
    week: usize,
    day: usize,
    shift_type_idx: usize,
}

macro_rules! assigned_shift_groups {
    () => {
        ConstraintFactory::<NrpPlan, HardSoftScore>::new()
            .for_each(NrpPlan::shifts())
            .group_by(
                nurse_soft_key_from_shift as fn(&NrpShift) -> NurseSoftKey,
                collect_vec(assigned_shift_projection as fn(&NrpShift) -> AssignedShiftProjection),
            )
            .complement_with_key(
                NrpPlan::nurse_indices(),
                nurse_soft_key_from_assigned_shift as fn(&NrpShift) -> Option<NurseSoftKey>,
                nurse_soft_key_from_nurse as fn(&NurseIndex) -> NurseSoftKey,
                |_nurse: &NurseIndex| Vec::new(),
            )
    };
}

macro_rules! assigned_shift_type_groups {
    () => {
        ConstraintFactory::<NrpPlan, HardSoftScore>::new()
            .for_each(NrpPlan::shifts())
            .group_by(
                shift_type_run_bounds_key_from_shift as fn(&NrpShift) -> ShiftTypeRunBoundsKey,
                collect_vec(assigned_shift_projection as fn(&NrpShift) -> AssignedShiftProjection),
            )
            .complement_with_key(
                NrpPlan::nurse_shift_type_indices(),
                shift_type_run_bounds_key_from_assigned_shift
                    as fn(&NrpShift) -> Option<ShiftTypeRunBoundsKey>,
                shift_type_run_bounds_key_from_fact
                    as fn(&NurseShiftTypeIndex) -> ShiftTypeRunBoundsKey,
                |_fact: &NurseShiftTypeIndex| Vec::new(),
            )
    };
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
        .penalize(shift_off_request_penalty as fn(&NrpShift) -> HardSoftScore)
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
        .penalize(HardSoftScore::of_hard(1))
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
        .penalize(HardSoftScore::of_hard(1))
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
        .penalize(HardSoftScore::of_hard(1))
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
        .penalize(HardSoftScore::of_hard(1))
        .named("adjacentForbiddenSuccession");

    let total_assignment_bounds = assigned_shift_groups!()
        .penalize(
            |key: &NurseSoftKey, assigned: &Vec<AssignedShiftProjection>| {
                total_assignment_bounds_penalty(key, assigned)
            },
        )
        .named("totalAssignmentBounds");

    let consecutive_work_bounds = assigned_shift_groups!()
        .penalize(
            |key: &NurseSoftKey, assigned: &Vec<AssignedShiftProjection>| {
                consecutive_work_bounds_penalty(key, assigned)
            },
        )
        .named("consecutiveWorkBounds");

    let consecutive_off_bounds = assigned_shift_groups!()
        .penalize(
            |key: &NurseSoftKey, assigned: &Vec<AssignedShiftProjection>| {
                consecutive_off_bounds_penalty(key, assigned)
            },
        )
        .named("consecutiveOffBounds");

    let consecutive_shift_type_bounds = assigned_shift_type_groups!()
        .penalize(
            |key: &ShiftTypeRunBoundsKey, assigned: &Vec<AssignedShiftProjection>| {
                consecutive_shift_type_bounds_penalty(key, assigned)
            },
        )
        .named("consecutiveShiftTypeBounds");

    let working_weekends = assigned_shift_groups!()
        .penalize(
            |key: &NurseSoftKey, assigned: &Vec<AssignedShiftProjection>| {
                working_weekends_penalty(key, assigned)
            },
        )
        .named("workingWeekends");

    let complete_weekends = assigned_shift_groups!()
        .penalize(
            |key: &NurseSoftKey, assigned: &Vec<AssignedShiftProjection>| {
                complete_weekends_penalty(key, assigned)
            },
        )
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

fn assigned_shift_projection(shift: &NrpShift) -> AssignedShiftProjection {
    AssignedShiftProjection {
        global_day: shift.global_day() as i64,
        week: shift.week,
        day: shift.day,
        shift_type_idx: shift.shift_type_idx,
    }
}

fn nurse_soft_key_from_shift(shift: &NrpShift) -> NurseSoftKey {
    let nurse_idx = shift.nurse_idx.unwrap_or(0);
    let data = shift.problem_data();
    let nurse = &data.nurses[nurse_idx];
    let contract = &data.contracts[nurse.contract_idx];
    let history = &data.nurse_history[nurse_idx];
    NurseSoftKey {
        nurse_idx,
        total_days: data.total_days() as i64,
        min_assignments: contract.min_assignments,
        max_assignments: contract.max_assignments,
        min_consecutive_working: contract.min_consecutive_working,
        max_consecutive_working: contract.max_consecutive_working,
        min_consecutive_off: contract.min_consecutive_off,
        max_consecutive_off: contract.max_consecutive_off,
        max_working_weekends: contract.max_working_weekends,
        complete_weekends: contract.complete_weekends,
        history_last_shift_type_idx: history.last_shift_type_idx,
        history_assignments: history.num_assignments,
        history_working_weekends: history.num_working_weekends,
        history_consecutive_working: history.num_consecutive_working,
        history_consecutive_off: history.num_consecutive_off,
    }
}

fn nurse_soft_key_from_assigned_shift(shift: &NrpShift) -> Option<NurseSoftKey> {
    shift.nurse_idx.map(|_| nurse_soft_key_from_shift(shift))
}

fn nurse_soft_key_from_nurse(nurse: &NurseIndex) -> NurseSoftKey {
    NurseSoftKey {
        nurse_idx: nurse.id,
        total_days: nurse.total_days,
        min_assignments: nurse.min_assignments,
        max_assignments: nurse.max_assignments,
        min_consecutive_working: nurse.min_consecutive_working,
        max_consecutive_working: nurse.max_consecutive_working,
        min_consecutive_off: nurse.min_consecutive_off,
        max_consecutive_off: nurse.max_consecutive_off,
        max_working_weekends: nurse.max_working_weekends,
        complete_weekends: nurse.complete_weekends,
        history_last_shift_type_idx: nurse.last_shift_type_idx,
        history_assignments: nurse.history_assignments,
        history_working_weekends: nurse.history_working_weekends,
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

fn shift_type_run_bounds_key_from_assigned_shift(
    shift: &NrpShift,
) -> Option<ShiftTypeRunBoundsKey> {
    shift
        .nurse_idx
        .map(|_| shift_type_run_bounds_key_from_shift(shift))
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

fn total_assignment_bounds_penalty(
    key: &NurseSoftKey,
    assigned: &[AssignedShiftProjection],
) -> HardSoftScore {
    let total_assigned = assigned.len() as i64 + key.history_assignments;
    let cost = if total_assigned < key.min_assignments {
        20 * (key.min_assignments - total_assigned)
    } else if total_assigned > key.max_assignments {
        20 * (total_assigned - key.max_assignments)
    } else {
        0
    };
    HardSoftScore::of_soft(cost)
}

fn consecutive_work_bounds_penalty(
    key: &NurseSoftKey,
    assigned: &[AssignedShiftProjection],
) -> HardSoftScore {
    let works_by_day = works_by_day(key.total_days, assigned);
    let initial = if key.history_last_shift_type_idx.is_some() {
        key.history_consecutive_working
    } else {
        0
    };
    HardSoftScore::of_soft(run_bounds_cost(
        &works_by_day,
        initial,
        key.min_consecutive_working,
        key.max_consecutive_working,
        30,
    ))
}

fn consecutive_off_bounds_penalty(
    key: &NurseSoftKey,
    assigned: &[AssignedShiftProjection],
) -> HardSoftScore {
    let off_by_day = works_by_day(key.total_days, assigned)
        .into_iter()
        .map(|works| !works)
        .collect::<Vec<_>>();
    let initial = if key.history_last_shift_type_idx.is_none() {
        key.history_consecutive_off
    } else {
        0
    };
    HardSoftScore::of_soft(run_bounds_cost(
        &off_by_day,
        initial,
        key.min_consecutive_off,
        key.max_consecutive_off,
        30,
    ))
}

fn consecutive_shift_type_bounds_penalty(
    key: &ShiftTypeRunBoundsKey,
    assigned: &[AssignedShiftProjection],
) -> HardSoftScore {
    let shift_type_by_day = shift_type_by_day(key.total_days, assigned);
    let matches_by_day = shift_type_by_day
        .into_iter()
        .map(|shift_type| shift_type == Some(key.shift_type_idx))
        .collect::<Vec<_>>();
    let initial = if key.history_last_shift_type_idx == Some(key.shift_type_idx) {
        key.history_consecutive_assignments
    } else {
        0
    };
    HardSoftScore::of_soft(run_bounds_cost(
        &matches_by_day,
        initial,
        key.min_consecutive,
        key.max_consecutive,
        15,
    ))
}

fn working_weekends_penalty(
    key: &NurseSoftKey,
    assigned: &[AssignedShiftProjection],
) -> HardSoftScore {
    let working_weekends = key.history_working_weekends + working_weekend_count(assigned);
    HardSoftScore::of_soft(max_bound_cost(
        working_weekends,
        key.max_working_weekends,
        30,
    ))
}

fn complete_weekends_penalty(
    key: &NurseSoftKey,
    assigned: &[AssignedShiftProjection],
) -> HardSoftScore {
    if !key.complete_weekends {
        return HardSoftScore::ZERO;
    }
    HardSoftScore::of_soft(complete_weekend_cost(key.total_days, assigned))
}

fn sorted_assigned(assigned: &[AssignedShiftProjection]) -> Vec<AssignedShiftProjection> {
    let mut sorted = assigned.to_vec();
    sorted.sort_unstable();
    sorted
}

fn works_by_day(total_days: i64, assigned: &[AssignedShiftProjection]) -> Vec<bool> {
    let mut works = vec![false; total_days.max(0) as usize];
    for shift in sorted_assigned(assigned) {
        let day = shift.global_day as usize;
        if day < works.len() {
            works[day] = true;
        }
    }
    works
}

fn shift_type_by_day(total_days: i64, assigned: &[AssignedShiftProjection]) -> Vec<Option<usize>> {
    let mut shift_types = vec![None; total_days.max(0) as usize];
    for shift in sorted_assigned(assigned) {
        let day = shift.global_day as usize;
        if day < shift_types.len() {
            shift_types[day] = Some(shift.shift_type_idx);
        }
    }
    shift_types
}

fn run_bounds_cost(days: &[bool], initial_run: i64, min: i64, max: i64, weight: i64) -> i64 {
    let mut cost = 0;
    let mut run = initial_run;
    for active in days {
        if *active {
            run += 1;
        } else {
            if run > 0 {
                cost += closed_bounds_cost(run, min, max, weight);
            }
            run = 0;
        }
    }
    cost + max_bound_cost(run, max, weight)
}

fn working_weekend_count(assigned: &[AssignedShiftProjection]) -> i64 {
    let mut weeks = Vec::new();
    for shift in sorted_assigned(assigned) {
        if shift.day >= 5 && !weeks.contains(&shift.week) {
            weeks.push(shift.week);
        }
    }
    weeks.len() as i64
}

fn complete_weekend_cost(total_days: i64, assigned: &[AssignedShiftProjection]) -> i64 {
    let works = works_by_day(total_days, assigned);
    let mut cost = 0;
    for week in 0..(works.len() / 7) {
        let sat_works = works[week * 7 + 5];
        let sun_works = works[week * 7 + 6];
        if sat_works != sun_works {
            cost += 30;
        }
    }
    cost
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
