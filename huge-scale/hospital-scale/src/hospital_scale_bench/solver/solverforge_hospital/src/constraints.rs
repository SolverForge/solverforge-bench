//! The hospital ruleset. Weights are mirrored exactly by the Timefold model
//! and the benchmark validator; `scripts/verify_model_parity.py` pins them.

use solverforge::prelude::*;

use crate::domain::{Employee, HospitalPlan, Shift};

const ASSIGNED_SHIFT_HARD: i64 = 1;
const REQUIRED_SKILL_HARD: i64 = 10;
const STRUCTURAL_MINUTE_HARD: i64 = 20;
const ONE_SHIFT_PER_DAY_HARD: i64 = 20;
const MINIMUM_REST_MINUTES: i64 = 600;
const PREFERENCE_SOFT: i64 = 10;

/// Ordered pairs of assigned shifts held by the same employee.
macro_rules! same_employee_pairs {
    () => {
        ConstraintFactory::<HospitalPlan, HardSoftScore>::new()
            .for_each(HospitalPlan::shifts())
            .filter(|shift: &Shift| shift.employee_idx.is_some())
            .join((
                ConstraintFactory::<HospitalPlan, HardSoftScore>::new()
                    .for_each(HospitalPlan::shifts()),
                joiner::equal_bi(
                    |left: &Shift| left.employee_idx,
                    |right: &Shift| right.employee_idx,
                ),
            ))
    };
}

/// Assigned shifts joined with the employee holding them.
macro_rules! assigned_with_employee {
    () => {
        ConstraintFactory::<HospitalPlan, HardSoftScore>::new()
            .for_each(HospitalPlan::shifts())
            .filter(|shift: &Shift| shift.employee_idx.is_some())
            .join((
                ConstraintFactory::<HospitalPlan, HardSoftScore>::new()
                    .for_each(HospitalPlan::employees()),
                joiner::equal_bi(
                    |shift: &Shift| shift.employee_idx,
                    |employee: &Employee| Some(employee.index),
                ),
            ))
    };
}

#[solverforge_constraints]
pub fn define_constraints() -> impl ConstraintSet<HospitalPlan, HardSoftScore> {
    let assigned_shift = ConstraintFactory::<HospitalPlan, HardSoftScore>::new()
        .for_each(HospitalPlan::shifts())
        .filter(|shift: &Shift| shift.employee_idx.is_none())
        .penalize(HardSoftScore::of_hard(ASSIGNED_SHIFT_HARD))
        .named("assigned_shift");

    let required_skill = assigned_with_employee!()
        .filter(|shift: &Shift, employee: &Employee| {
            !employee.skills.contains(&shift.required_skill)
        })
        .penalize(HardSoftScore::of_hard(REQUIRED_SKILL_HARD))
        .named("required_skill");

    let overlapping_shift = same_employee_pairs!()
        .filter(|left: &Shift, right: &Shift| {
            left.index < right.index && overlap_minutes(left, right) > 0
        })
        .penalize(hard_weight(|left: &Shift, right: &Shift| {
            HardSoftScore::of_hard(STRUCTURAL_MINUTE_HARD * overlap_minutes(left, right))
        }))
        .named("overlapping_shift");

    let minimum_rest = same_employee_pairs!()
        .filter(|left: &Shift, right: &Shift| {
            left.index < right.index && rest_shortfall(left, right) > 0
        })
        .penalize(hard_weight(|left: &Shift, right: &Shift| {
            HardSoftScore::of_hard(STRUCTURAL_MINUTE_HARD * rest_shortfall(left, right))
        }))
        .named("minimum_rest");

    let one_shift_per_day = same_employee_pairs!()
        .filter(|left: &Shift, right: &Shift| {
            left.index < right.index
                && left.first_day <= right.last_day
                && right.first_day <= left.last_day
        })
        .penalize(HardSoftScore::of_hard(ONE_SHIFT_PER_DAY_HARD))
        .named("one_shift_per_day");

    let unavailable_employee = assigned_with_employee!()
        .filter(|shift: &Shift, employee: &Employee| unavailable_minutes(shift, employee) > 0)
        .penalize(hard_weight(|shift: &Shift, employee: &Employee| {
            HardSoftScore::of_hard(STRUCTURAL_MINUTE_HARD * unavailable_minutes(shift, employee))
        }))
        .named("unavailable_employee");

    let undesired_day = assigned_with_employee!()
        .filter(|shift: &Shift, employee: &Employee| {
            touched_count(shift, &employee.undesired_days) > 0
        })
        .penalize(|shift: &Shift, employee: &Employee| {
            HardSoftScore::of_soft(PREFERENCE_SOFT * touched_count(shift, &employee.undesired_days))
        })
        .named("undesired_day");

    let desired_day = assigned_with_employee!()
        .filter(|shift: &Shift, employee: &Employee| {
            touched_count(shift, &employee.desired_days) > 0
        })
        .reward(|shift: &Shift, employee: &Employee| {
            HardSoftScore::of_soft(PREFERENCE_SOFT * touched_count(shift, &employee.desired_days))
        })
        .named("desired_day");

    let balance_assignments = ConstraintFactory::<HospitalPlan, HardSoftScore>::new()
        .for_each(HospitalPlan::shifts())
        .filter(|shift: &Shift| shift.employee_idx.is_some())
        .group_by(
            |shift: &Shift| shift.employee_idx.unwrap_or(usize::MAX),
            count(),
        )
        .penalize(|_employee: &usize, assigned: &usize| {
            let assigned = *assigned as i64;
            HardSoftScore::of_soft(assigned * assigned)
        })
        .named("balance_assignments");

    (
        assigned_shift,
        required_skill,
        overlapping_shift,
        minimum_rest,
        one_shift_per_day,
        unavailable_employee,
        undesired_day,
        desired_day,
        balance_assignments,
    )
}

fn overlap_minutes(left: &Shift, right: &Shift) -> i64 {
    (left.end.min(right.end) - left.start.max(right.start)).max(0)
}

/// Minutes short of the 10-hour rest between two non-overlapping shifts.
fn rest_shortfall(left: &Shift, right: &Shift) -> i64 {
    let gap = if left.end <= right.start {
        right.start - left.end
    } else if right.end <= left.start {
        left.start - right.end
    } else {
        return 0;
    };
    (MINIMUM_REST_MINUTES - gap).max(0)
}

fn unavailable_minutes(shift: &Shift, employee: &Employee) -> i64 {
    employee
        .unavailable_days
        .iter()
        .map(|day| shift.minutes_on(*day))
        .sum()
}

fn touched_count(shift: &Shift, days: &[i64]) -> i64 {
    days.iter().filter(|day| shift.touches(**day)).count() as i64
}
