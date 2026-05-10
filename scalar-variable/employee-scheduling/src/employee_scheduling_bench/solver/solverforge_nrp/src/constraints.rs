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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct AssignedNurseShift {
    nurse_key: NurseSoftKey,
    global_day: i64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct AssignedShiftType {
    key: ShiftTypeRunBoundsKey,
    global_day: i64,
}

macro_rules! assigned_nurse_shifts {
    () => {
        ConstraintFactory::<NrpPlan, HardSoftScore>::new()
            .for_each(NrpPlan::shifts())
            .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
            .join((
                ConstraintFactory::<NrpPlan, HardSoftScore>::new()
                    .for_each(NrpPlan::nurse_indices()),
                joiner::equal_bi(
                    |shift: &NrpShift| shift.nurse_idx,
                    |nurse: &NurseIndex| Some(nurse.id),
                ),
            ))
            .project(assigned_nurse_shift as fn(&NrpShift, &NurseIndex) -> AssignedNurseShift)
    };
}

macro_rules! assigned_shift_types {
    () => {
        ConstraintFactory::<NrpPlan, HardSoftScore>::new()
            .for_each(NrpPlan::shifts())
            .filter(|shift: &NrpShift| shift.nurse_idx.is_some())
            .join((
                ConstraintFactory::<NrpPlan, HardSoftScore>::new()
                    .for_each(NrpPlan::nurse_shift_type_indices()),
                joiner::equal_bi(
                    |shift: &NrpShift| shift.nurse_idx.map(|nurse| (nurse, shift.shift_type_idx)),
                    |fact: &NurseShiftTypeIndex| Some((fact.nurse_idx, fact.shift_type_idx)),
                ),
            ))
            .project(
                assigned_shift_type as fn(&NrpShift, &NurseShiftTypeIndex) -> AssignedShiftType,
            )
    };
}

macro_rules! nurses_without_assignments {
    () => {
        ConstraintFactory::<NrpPlan, HardSoftScore>::new()
            .for_each(NrpPlan::nurse_indices())
            .if_not_exists((
                ConstraintFactory::<NrpPlan, HardSoftScore>::new()
                    .for_each(NrpPlan::shifts())
                    .filter(|shift: &NrpShift| shift.nurse_idx.is_some()),
                joiner::equal_bi(
                    |nurse: &NurseIndex| Some(nurse.id),
                    |shift: &NrpShift| shift.nurse_idx,
                ),
            ))
    };
}

macro_rules! shift_types_without_assignments {
    () => {
        ConstraintFactory::<NrpPlan, HardSoftScore>::new()
            .for_each(NrpPlan::nurse_shift_type_indices())
            .if_not_exists((
                ConstraintFactory::<NrpPlan, HardSoftScore>::new()
                    .for_each(NrpPlan::shifts())
                    .filter(|shift: &NrpShift| shift.nurse_idx.is_some()),
                joiner::equal_bi(
                    |fact: &NurseShiftTypeIndex| Some((fact.nurse_idx, fact.shift_type_idx)),
                    |shift: &NrpShift| shift.nurse_idx.map(|nurse| (nurse, shift.shift_type_idx)),
                ),
            ))
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

    let total_assignment_bounds = assigned_nurse_shifts!()
        .group_by(
            |row: &AssignedNurseShift| row.nurse_key,
            indexed_presence(|row: &AssignedNurseShift| row.global_day),
        )
        .penalize(|key: &NurseSoftKey, presence: &IndexedPresence| {
            total_assignment_bounds_penalty(key, presence)
        })
        .named("totalAssignmentBounds");

    let empty_total_assignment_bounds = nurses_without_assignments!()
        .penalize(empty_total_assignment_bounds_penalty as fn(&NurseIndex) -> HardSoftScore)
        .named("totalAssignmentBounds");

    let consecutive_work_bounds = assigned_nurse_shifts!()
        .group_by(
            |row: &AssignedNurseShift| row.nurse_key,
            indexed_presence(|row: &AssignedNurseShift| row.global_day),
        )
        .penalize(|key: &NurseSoftKey, presence: &IndexedPresence| {
            consecutive_work_bounds_penalty(key, presence)
        })
        .named("consecutiveWorkBounds");

    let empty_consecutive_work_bounds = nurses_without_assignments!()
        .penalize(empty_consecutive_work_bounds_penalty as fn(&NurseIndex) -> HardSoftScore)
        .named("consecutiveWorkBounds");

    let consecutive_off_bounds = assigned_nurse_shifts!()
        .group_by(
            |row: &AssignedNurseShift| row.nurse_key,
            indexed_presence(|row: &AssignedNurseShift| row.global_day),
        )
        .penalize(|key: &NurseSoftKey, presence: &IndexedPresence| {
            consecutive_off_bounds_penalty(key, presence)
        })
        .named("consecutiveOffBounds");

    let empty_consecutive_off_bounds = nurses_without_assignments!()
        .penalize(empty_consecutive_off_bounds_penalty as fn(&NurseIndex) -> HardSoftScore)
        .named("consecutiveOffBounds");

    let consecutive_shift_type_bounds = assigned_shift_types!()
        .group_by(
            |row: &AssignedShiftType| row.key,
            indexed_presence(|row: &AssignedShiftType| row.global_day),
        )
        .penalize(|key: &ShiftTypeRunBoundsKey, presence: &IndexedPresence| {
            consecutive_shift_type_bounds_penalty(key, presence)
        })
        .named("consecutiveShiftTypeBounds");

    let empty_consecutive_shift_type_bounds = shift_types_without_assignments!()
        .penalize(
            empty_consecutive_shift_type_bounds_penalty
                as fn(&NurseShiftTypeIndex) -> HardSoftScore,
        )
        .named("consecutiveShiftTypeBounds");

    let working_weekends = assigned_nurse_shifts!()
        .group_by(
            |row: &AssignedNurseShift| row.nurse_key,
            indexed_presence(|row: &AssignedNurseShift| row.global_day),
        )
        .penalize(|key: &NurseSoftKey, presence: &IndexedPresence| {
            working_weekends_penalty(key, presence)
        })
        .named("workingWeekends");

    let empty_working_weekends = nurses_without_assignments!()
        .penalize(empty_working_weekends_penalty as fn(&NurseIndex) -> HardSoftScore)
        .named("workingWeekends");

    let complete_weekends = assigned_nurse_shifts!()
        .group_by(
            |row: &AssignedNurseShift| row.nurse_key,
            indexed_presence(|row: &AssignedNurseShift| row.global_day),
        )
        .penalize(|key: &NurseSoftKey, presence: &IndexedPresence| {
            complete_weekends_penalty(key, presence)
        })
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
        empty_total_assignment_bounds,
        consecutive_work_bounds,
        empty_consecutive_work_bounds,
        consecutive_off_bounds,
        empty_consecutive_off_bounds,
        consecutive_shift_type_bounds,
        empty_consecutive_shift_type_bounds,
        working_weekends,
        empty_working_weekends,
        complete_weekends,
    )
}

fn assigned_nurse_shift(shift: &NrpShift, nurse: &NurseIndex) -> AssignedNurseShift {
    AssignedNurseShift {
        nurse_key: nurse_soft_key_from_nurse(nurse),
        global_day: shift.global_day() as i64,
    }
}

fn assigned_shift_type(shift: &NrpShift, fact: &NurseShiftTypeIndex) -> AssignedShiftType {
    AssignedShiftType {
        key: shift_type_run_bounds_key_from_fact(fact),
        global_day: shift.global_day() as i64,
    }
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
    presence: &IndexedPresence,
) -> HardSoftScore {
    let total_assigned = presence.item_count() as i64 + key.history_assignments;
    let cost = if total_assigned < key.min_assignments {
        20 * (key.min_assignments - total_assigned)
    } else if total_assigned > key.max_assignments {
        20 * (total_assigned - key.max_assignments)
    } else {
        0
    };
    HardSoftScore::of_soft(cost)
}

fn empty_total_assignment_bounds_penalty(nurse: &NurseIndex) -> HardSoftScore {
    let total_assigned = nurse.history_assignments;
    let cost = if total_assigned < nurse.min_assignments {
        20 * (nurse.min_assignments - total_assigned)
    } else if total_assigned > nurse.max_assignments {
        20 * (total_assigned - nurse.max_assignments)
    } else {
        0
    };
    HardSoftScore::of_soft(cost)
}

fn consecutive_work_bounds_penalty(
    key: &NurseSoftKey,
    presence: &IndexedPresence,
) -> HardSoftScore {
    let initial = if key.history_last_shift_type_idx.is_some() {
        key.history_consecutive_working
    } else {
        0
    };
    HardSoftScore::of_soft(run_bounds_cost(
        &presence.runs(),
        key.total_days,
        initial,
        key.min_consecutive_working,
        key.max_consecutive_working,
        30,
    ))
}

fn empty_consecutive_work_bounds_penalty(nurse: &NurseIndex) -> HardSoftScore {
    let cost = if nurse.last_shift_type_idx.is_some() {
        closed_bounds_cost(
            nurse.history_consecutive_working,
            nurse.min_consecutive_working,
            nurse.max_consecutive_working,
            30,
        )
    } else {
        0
    };
    HardSoftScore::of_soft(cost)
}

fn consecutive_off_bounds_penalty(key: &NurseSoftKey, presence: &IndexedPresence) -> HardSoftScore {
    let initial = if key.history_last_shift_type_idx.is_none() {
        key.history_consecutive_off
    } else {
        0
    };
    HardSoftScore::of_soft(run_bounds_cost(
        &presence.complement_runs(0..key.total_days),
        key.total_days,
        initial,
        key.min_consecutive_off,
        key.max_consecutive_off,
        30,
    ))
}

fn empty_consecutive_off_bounds_penalty(nurse: &NurseIndex) -> HardSoftScore {
    let initial = if nurse.last_shift_type_idx.is_none() {
        nurse.history_consecutive_off
    } else {
        0
    };
    HardSoftScore::of_soft(max_bound_cost(
        initial + nurse.total_days,
        nurse.max_consecutive_off,
        30,
    ))
}

fn consecutive_shift_type_bounds_penalty(
    key: &ShiftTypeRunBoundsKey,
    presence: &IndexedPresence,
) -> HardSoftScore {
    let initial = if key.history_last_shift_type_idx == Some(key.shift_type_idx) {
        key.history_consecutive_assignments
    } else {
        0
    };
    HardSoftScore::of_soft(run_bounds_cost(
        &presence.runs(),
        key.total_days,
        initial,
        key.min_consecutive,
        key.max_consecutive,
        15,
    ))
}

fn empty_consecutive_shift_type_bounds_penalty(fact: &NurseShiftTypeIndex) -> HardSoftScore {
    let cost = if fact.history_last_shift_type_idx == Some(fact.shift_type_idx) {
        closed_bounds_cost(
            fact.history_consecutive_assignments,
            fact.min_consecutive,
            fact.max_consecutive,
            15,
        )
    } else {
        0
    };
    HardSoftScore::of_soft(cost)
}

fn working_weekends_penalty(key: &NurseSoftKey, presence: &IndexedPresence) -> HardSoftScore {
    let working_weekends = key.history_working_weekends + working_weekend_count(key, presence);
    HardSoftScore::of_soft(max_bound_cost(
        working_weekends,
        key.max_working_weekends,
        30,
    ))
}

fn empty_working_weekends_penalty(nurse: &NurseIndex) -> HardSoftScore {
    HardSoftScore::of_soft(max_bound_cost(
        nurse.history_working_weekends,
        nurse.max_working_weekends,
        30,
    ))
}

fn complete_weekends_penalty(key: &NurseSoftKey, presence: &IndexedPresence) -> HardSoftScore {
    if !key.complete_weekends {
        return HardSoftScore::ZERO;
    }
    HardSoftScore::of_soft(complete_weekend_cost(key, presence))
}

fn run_bounds_cost(
    runs: &Runs,
    total_days: i64,
    initial_run: i64,
    min: i64,
    max: i64,
    weight: i64,
) -> i64 {
    let mut cost = 0;
    let mut initial_consumed = false;
    for run in runs.runs() {
        let mut length = run.point_count() as i64;
        if !initial_consumed && initial_run > 0 {
            if run.start() == 0 {
                length += initial_run;
            } else {
                cost += closed_bounds_cost(initial_run, min, max, weight);
            }
            initial_consumed = true;
        }
        if run.end().saturating_add(1) >= total_days {
            cost += max_bound_cost(length, max, weight);
        } else {
            cost += closed_bounds_cost(length, min, max, weight);
        }
    }
    if !initial_consumed && initial_run > 0 {
        cost += closed_bounds_cost(initial_run, min, max, weight);
    }
    cost
}

fn working_weekend_count(key: &NurseSoftKey, presence: &IndexedPresence) -> i64 {
    let week_count = (key.total_days.max(0) as usize) / 7;
    (0..week_count)
        .filter(|week| {
            let start = (*week as i64) * 7 + 5;
            presence.any_in(start..start + 2)
        })
        .count() as i64
}

fn complete_weekend_cost(key: &NurseSoftKey, presence: &IndexedPresence) -> i64 {
    let week_count = (key.total_days.max(0) as usize) / 7;
    let mut cost = 0;
    for week in 0..week_count {
        let saturday = week as i64 * 7 + 5;
        let sat_works = presence.contains(saturday);
        let sun_works = presence.contains(saturday + 1);
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
