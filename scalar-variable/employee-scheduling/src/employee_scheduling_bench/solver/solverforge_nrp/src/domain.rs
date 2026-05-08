use serde::Deserialize;
use solverforge::prelude::*;

#[derive(Clone, Deserialize)]
pub struct ContractData {
    pub id: String,
    pub min_assignments: i64,
    pub max_assignments: i64,
    pub min_consecutive_working: i64,
    pub max_consecutive_working: i64,
    pub min_consecutive_off: i64,
    pub max_consecutive_off: i64,
    pub max_working_weekends: i64,
    pub complete_weekends: bool,
}

#[derive(Clone, Deserialize)]
pub struct ShiftTypeData {
    pub id: String,
    pub min_consecutive: i64,
    pub max_consecutive: i64,
}

#[derive(Clone, Deserialize)]
pub struct NurseHistoryData {
    pub nurse_idx: usize,
    pub num_assignments: i64,
    pub num_working_weekends: i64,
    pub last_shift_type_idx: Option<usize>,
    pub num_consecutive_assignments: i64,
    pub num_consecutive_working: i64,
    pub num_consecutive_off: i64,
}

pub struct ProblemData {
    pub nurses: Vec<NurseData>,
    pub contracts: Vec<ContractData>,
    pub shift_types: Vec<ShiftTypeData>,
    pub forbidden: Vec<(usize, Vec<usize>)>,
    pub forbidden_successors: Vec<Vec<usize>>,
    pub shift_off_requests: Vec<(usize, usize, usize)>,
    pub shift_off_requests_by_nurse_day: Vec<Vec<Vec<usize>>>,
    pub nurse_history: Vec<NurseHistoryData>,
    pub num_weeks: usize,
    pub num_shift_types: usize,
}

unsafe impl Send for ProblemData {}
unsafe impl Sync for ProblemData {}

impl ProblemData {
    pub fn total_days(&self) -> usize {
        self.num_weeks * 7
    }

    pub(crate) fn nurse_has_skill(&self, nurse_idx: usize, skill_idx: usize) -> bool {
        self.nurses
            .get(nurse_idx)
            .is_some_and(|nurse| nurse.skills.contains(&skill_idx))
    }

    pub(crate) fn successor_allowed(&self, previous: Option<usize>, current: usize) -> bool {
        previous.is_none_or(|previous| {
            !self
                .forbidden_successors
                .get(previous)
                .is_some_and(|successors| successors.contains(&current))
        })
    }

    pub(crate) fn history_allows(&self, nurse_idx: usize, current_shift_type: usize) -> bool {
        self.nurse_history
            .get(nurse_idx)
            .is_none_or(|history| self.successor_allowed(history.last_shift_type_idx, current_shift_type))
    }

    pub fn shift_off_requested(
        &self,
        nurse_idx: usize,
        global_day: usize,
        shift_type_idx: usize,
    ) -> bool {
        self.shift_off_requests_by_nurse_day
            .get(nurse_idx)
            .and_then(|days| days.get(global_day))
            .is_some_and(|requests| {
                requests
                    .iter()
                    .any(|request| *request == usize::MAX || *request == shift_type_idx)
            })
    }
}

#[derive(Clone)]
pub struct NurseData {
    pub index: usize,
    pub id: String,
    pub contract_idx: usize,
    pub skills: Vec<usize>,
}

#[problem_fact]
pub struct NurseIndex {
    #[planning_id]
    pub id: usize,
    pub skills: Vec<usize>,
    pub last_shift_type_idx: Option<usize>,
    pub history_assignments: i64,
    pub history_working_weekends: i64,
    pub history_consecutive_assignments: i64,
    pub history_consecutive_working: i64,
    pub history_consecutive_off: i64,
    pub total_days: i64,
    pub min_assignments: i64,
    pub max_assignments: i64,
    pub min_consecutive_working: i64,
    pub max_consecutive_working: i64,
    pub min_consecutive_off: i64,
    pub max_consecutive_off: i64,
    pub max_working_weekends: i64,
    pub complete_weekends: bool,
}

#[problem_fact]
pub struct NurseShiftTypeIndex {
    #[planning_id]
    pub id: usize,
    pub nurse_idx: usize,
    pub shift_type_idx: usize,
    pub min_consecutive: i64,
    pub max_consecutive: i64,
    pub history_last_shift_type_idx: Option<usize>,
    pub history_consecutive_assignments: i64,
    pub total_days: i64,
}

#[planning_entity]
pub struct NrpShift {
    #[planning_id]
    pub id: usize,
    pub week: usize,
    pub day: usize,
    pub shift_type_idx: usize,
    pub skill_idx: usize,
    pub is_minimum: bool,
    pub forbidden_predecessors: Vec<usize>,
    pub shift_off_request_nurses: Vec<usize>,
    pub data: *const ProblemData,
    #[planning_variable(
        value_range_provider = "nurse_indices",
        allows_unassigned = true,
        candidate_values = "nurse_candidates_for_shift",
        nearby_value_candidates = "nearby_nurse_candidates_for_shift",
        nearby_entity_candidates = "nearby_shift_candidates",
        nearby_value_distance_meter = "shift_to_nurse_distance",
        nearby_entity_distance_meter = "shift_to_shift_distance"
    )]
    pub nurse_idx: Option<usize>,
}

unsafe impl Send for NrpShift {}
unsafe impl Sync for NrpShift {}

impl NrpShift {
    pub(crate) fn global_day(&self) -> usize {
        self.week * 7 + self.day
    }

    pub(crate) fn problem_data(&self) -> &ProblemData {
        unsafe { &*self.data }
    }
}

#[planning_solution(
    constraints = "crate::constraints::define_constraints",
    scalar_groups = "crate::domain::scalar_groups",
    solver_toml = "../solver.toml"
)]
pub struct NrpPlan {
    #[planning_entity_collection]
    pub shifts: Vec<NrpShift>,
    #[problem_fact_collection]
    pub nurse_indices: Vec<NurseIndex>,
    #[problem_fact_collection]
    pub nurse_shift_type_indices: Vec<NurseShiftTypeIndex>,
    #[planning_score]
    pub score: Option<HardSoftScore>,
    pub shift_nurse_candidates: Vec<Vec<usize>>,
    pub shift_indices: Vec<usize>,
    pub data: *const ProblemData,
}

unsafe impl Send for NrpPlan {}
unsafe impl Sync for NrpPlan {}

impl NrpPlan {
    pub fn problem_data(&self) -> &ProblemData {
        unsafe { &*self.data }
    }

    pub(crate) fn assigned_shift_types_for_nurse_day_except(
        &self,
        nurse_idx: usize,
        global_day: usize,
        excluded_entity_index: Option<usize>,
    ) -> Vec<usize> {
        self.shifts
            .iter()
            .enumerate()
            .filter(|(entity_index, shift)| {
                Some(*entity_index) != excluded_entity_index
                    && shift.nurse_idx == Some(nurse_idx)
                    && shift.global_day() == global_day
            })
            .map(|(_, shift)| shift.shift_type_idx)
            .collect()
    }

    pub(crate) fn has_assignment_for_nurse_day_except(
        &self,
        nurse_idx: usize,
        global_day: usize,
        excluded_entity_index: Option<usize>,
    ) -> bool {
        self.shifts.iter().enumerate().any(|(entity_index, shift)| {
            Some(entity_index) != excluded_entity_index
                && shift.nurse_idx == Some(nurse_idx)
                && shift.global_day() == global_day
        })
    }

    pub(crate) fn assignment_temporally_allowed(
        &self,
        entity_index: usize,
        nurse_idx: usize,
    ) -> bool {
        let Some(shift) = self.shifts.get(entity_index) else {
            return false;
        };
        let data = self.problem_data();
        if !data.nurse_has_skill(nurse_idx, shift.skill_idx) {
            return false;
        }
        let global_day = shift.global_day();
        if self.has_assignment_for_nurse_day_except(nurse_idx, global_day, Some(entity_index)) {
            return false;
        }

        if !self.predecessors_allow_assignment(nurse_idx, global_day, shift.shift_type_idx, Some(entity_index)) {
            return false;
        }
        self.assignment_allows_successors(nurse_idx, global_day, shift.shift_type_idx, Some(entity_index))
    }

    pub(crate) fn predecessors_allow_assignment(
        &self,
        nurse_idx: usize,
        global_day: usize,
        shift_type_idx: usize,
        excluded_entity_index: Option<usize>,
    ) -> bool {
        let data = self.problem_data();
        if global_day == 0 {
            return data.history_allows(nurse_idx, shift_type_idx);
        }

        self.assigned_shift_types_for_nurse_day_except(
            nurse_idx,
            global_day - 1,
            excluded_entity_index,
        )
        .into_iter()
        .all(|previous| data.successor_allowed(Some(previous), shift_type_idx))
    }

    pub(crate) fn assignment_allows_successors(
        &self,
        nurse_idx: usize,
        global_day: usize,
        shift_type_idx: usize,
        excluded_entity_index: Option<usize>,
    ) -> bool {
        let data = self.problem_data();
        if global_day + 1 >= data.total_days() {
            return true;
        }

        self.assigned_shift_types_for_nurse_day_except(
            nurse_idx,
            global_day + 1,
            excluded_entity_index,
        )
        .into_iter()
        .all(|next| data.successor_allowed(Some(shift_type_idx), next))
    }

}

pub(super) fn nurse_candidates_for_shift(
    solution: &NrpPlan,
    entity_index: usize,
    _variable_index: usize,
) -> &[usize] {
    solution
        .shift_nurse_candidates
        .get(entity_index)
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

pub fn scalar_groups() -> Vec<ScalarGroup<NrpPlan>> {
    let shifts = NrpPlan::shifts();
    vec![
        ScalarGroup::assignment("shift_nurse_assignment", shifts.scalar("nurse_idx"))
            .with_required_entity(shift_assignment_required)
            .with_capacity_key(shift_nurse_day_capacity_key)
            .with_position_key(shift_position_key)
            .with_sequence_key(shift_nurse_sequence_key)
            .with_entity_order(shift_assignment_entity_order_key)
            .with_value_order(shift_assignment_value_order_key)
            .with_limits(ScalarGroupLimits {
                max_augmenting_depth: Some(4),
                max_rematch_size: Some(8),
                ..ScalarGroupLimits::new()
            }),
    ]
}

fn shift_assignment_required(solution: &NrpPlan, entity_index: usize) -> bool {
    solution
        .shifts
        .get(entity_index)
        .is_some_and(|shift| shift.is_minimum)
}

fn shift_nurse_day_capacity_key(
    solution: &NrpPlan,
    entity_index: usize,
    nurse_idx: usize,
) -> Option<usize> {
    let shift = solution.shifts.get(entity_index)?;
    let global_day = shift.week * 7 + shift.day;
    Some(nurse_idx * solution.problem_data().total_days() + global_day)
}

fn shift_position_key(solution: &NrpPlan, entity_index: usize) -> i64 {
    let Some(shift) = solution.shifts.get(entity_index) else {
        return i64::MAX;
    };
    let global_day = match i64::try_from(shift.global_day()) {
        Ok(day) => day,
        Err(_) => return i64::MAX,
    };
    let shift_type = match i64::try_from(shift.shift_type_idx) {
        Ok(shift_type) => shift_type,
        Err(_) => return i64::MAX,
    };
    let skill = match i64::try_from(shift.skill_idx) {
        Ok(skill) => skill,
        Err(_) => return i64::MAX,
    };
    global_day
        .saturating_mul(10_000)
        .saturating_add(shift_type.saturating_mul(100))
        .saturating_add(skill)
}

fn shift_nurse_sequence_key(
    solution: &NrpPlan,
    entity_index: usize,
    _nurse_idx: usize,
) -> Option<usize> {
    solution
        .shifts
        .get(entity_index)
        .map(NrpShift::global_day)
}

fn shift_assignment_entity_order_key(solution: &NrpPlan, entity_index: usize) -> i64 {
    let Some(shift) = solution.shifts.get(entity_index) else {
        return i64::MAX;
    };
    let priority = if shift.is_minimum { 0_i64 } else { 1_i64 };
    priority
        .saturating_mul(1_000_000_000)
        .saturating_add(shift_position_key(solution, entity_index))
}

fn shift_assignment_value_order_key(
    solution: &NrpPlan,
    entity_index: usize,
    nurse_idx: usize,
) -> i64 {
    let Some(shift) = solution.shifts.get(entity_index) else {
        return i64::MAX;
    };
    assignment_value_order_key(solution, shift, nurse_idx)
}

fn assignment_value_order_key(solution: &NrpPlan, shift: &NrpShift, nurse_idx: usize) -> i64 {
    let data = solution.problem_data();
    let global_day = shift.week * 7 + shift.day;
    let has_skill = data
        .nurses
        .get(nurse_idx)
        .is_some_and(|nurse| nurse.skills.contains(&shift.skill_idx));
    let skill_penalty = if has_skill { 0 } else { 1_000_000 };
    let same_day_conflict = solution
        .shifts
        .iter()
        .any(|other| {
            other.nurse_idx == Some(nurse_idx)
                && other.week == shift.week
                && other.day == shift.day
        });
    let same_day_penalty = if same_day_conflict { 100_000 } else { 0 };
    let request_penalty = if data.shift_off_requested(nurse_idx, global_day, shift.shift_type_idx) {
        10_000
    } else {
        0
    };
    let temporal_penalty = if solution.assignment_temporally_allowed(shift.id, nurse_idx) {
        0
    } else {
        500_000
    };
    let existing_assignments = solution
        .shifts
        .iter()
        .filter(|other| other.nurse_idx == Some(nurse_idx))
        .count();
    let existing_assignments = i64::try_from(existing_assignments).unwrap_or(i64::MAX);

    skill_penalty
        + temporal_penalty
        + same_day_penalty
        + request_penalty
        + existing_assignments.saturating_mul(100)
        + i64::try_from(nurse_idx).unwrap_or(i64::MAX)
}

pub(super) fn nearby_nurse_candidates_for_shift(
    solution: &NrpPlan,
    entity_index: usize,
    variable_index: usize,
) -> &[usize] {
    nurse_candidates_for_shift(solution, entity_index, variable_index)
}

pub(super) fn nearby_shift_candidates(
    solution: &NrpPlan,
    _entity_index: usize,
    _variable_index: usize,
) -> &[usize] {
    solution.shift_indices.as_slice()
}

pub(super) fn shift_to_nurse_distance(
    solution: &NrpPlan,
    shift: &NrpShift,
    nurse_index: usize,
) -> f64 {
    let data = solution.problem_data();
    let Some(nurse) = data.nurses.get(nurse_index) else {
        return f64::INFINITY;
    };

    let mut distance = if nurse.skills.contains(&shift.skill_idx) {
        0.0
    } else {
        10_000.0
    };

    let global_day = shift.week * 7 + shift.day;
    if data.shift_off_requested(nurse_index, global_day, shift.shift_type_idx) {
        distance += 100.0;
    }
    if !solution.assignment_temporally_allowed(shift.id, nurse_index) {
        distance += 5_000.0;
    }

    distance + solution
        .shifts
        .iter()
        .filter(|other| other.nurse_idx == Some(nurse_index))
        .count() as f64
}

pub(super) fn shift_to_shift_distance(
    _solution: &NrpPlan,
    left: &NrpShift,
    right: &NrpShift,
) -> f64 {
    let left_day = left.week * 7 + left.day;
    let right_day = right.week * 7 + right.day;
    let day_distance = left_day.abs_diff(right_day).min(14) as f64;
    let skill_distance = if left.skill_idx == right.skill_idx {
        0.0
    } else {
        4.0
    };
    let shift_type_distance = if left.shift_type_idx == right.shift_type_idx {
        0.0
    } else {
        2.0
    };

    day_distance + skill_distance + shift_type_distance
}
