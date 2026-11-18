use solverforge::prelude::*;

pub const MINUTES_PER_DAY: i64 = 1440;

/// Staff member: a problem fact the solver reads but never moves.
#[problem_fact]
pub struct Employee {
    #[planning_id]
    pub index: usize,
    pub home_hub: usize,
    pub skills: Vec<usize>,
    pub unavailable_days: Vec<i64>,
    pub desired_days: Vec<i64>,
    pub undesired_days: Vec<i64>,
}

/// Work item that needs exactly one employee; the only planning entity.
#[planning_entity]
pub struct Shift {
    #[planning_id]
    pub index: usize,
    pub start: i64,
    pub end: i64,
    pub first_day: i64,
    pub last_day: i64,
    pub hub: usize,
    pub required_skill: usize,
    #[planning_variable(
        value_range_provider = "employees",
        allows_unassigned = true,
        candidate_values = "shift_employee_candidates",
        nearby_value_candidates = "shift_nearby_employee_candidates",
        nearby_entity_candidates = "shift_nearby_shift_candidates",
        nearby_value_distance_meter = "shift_to_employee_distance",
        nearby_entity_distance_meter = "shift_to_shift_distance"
    )]
    pub employee_idx: Option<usize>,
}

impl Shift {
    /// Whether the shift touches calendar day `day` for at least one minute.
    pub fn touches(&self, day: i64) -> bool {
        self.first_day <= day && day <= self.last_day
    }

    /// Minutes of the shift that fall inside calendar day `day`.
    pub fn minutes_on(&self, day: i64) -> i64 {
        let day_start = day * MINUTES_PER_DAY;
        let day_end = day_start + MINUTES_PER_DAY;
        (self.end.min(day_end) - self.start.max(day_start)).max(0)
    }
}

#[planning_solution(
    constraints = "crate::constraints::define_constraints",
    config = "crate::domain::solver_config_for_plan",
    solver_toml = "../solver.toml"
)]
pub struct HospitalPlan {
    #[planning_entity_collection]
    pub shifts: Vec<Shift>,
    #[problem_fact_collection]
    pub employees: Vec<Employee>,
    #[planning_score]
    pub score: Option<HardSoftScore>,
    /// Employees holding each skill: the shared candidate domain per skill.
    pub skill_candidates: Vec<Vec<usize>>,
    /// Bounded same-skill neighbourhood per shift, in start order.
    pub shift_neighbours: Vec<Vec<usize>>,
    pub hub_positions: Vec<(i64, i64)>,
    pub time_limit_secs: u64,
}

pub fn solver_config_for_plan(
    solution: &HospitalPlan,
    config: solverforge::SolverConfig,
) -> solverforge::SolverConfig {
    config.with_termination_seconds(solution.time_limit_secs.max(1))
}

pub(super) fn shift_employee_candidates(
    solution: &HospitalPlan,
    entity_index: usize,
    _variable_index: usize,
) -> &[usize] {
    solution
        .shifts
        .get(entity_index)
        .and_then(|shift| solution.skill_candidates.get(shift.required_skill))
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

pub(super) fn shift_nearby_employee_candidates(
    solution: &HospitalPlan,
    entity_index: usize,
    variable_index: usize,
) -> &[usize] {
    shift_employee_candidates(solution, entity_index, variable_index)
}

pub(super) fn shift_nearby_shift_candidates(
    solution: &HospitalPlan,
    entity_index: usize,
    _variable_index: usize,
) -> &[usize] {
    solution
        .shift_neighbours
        .get(entity_index)
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

// Nearby meters run during move generation: constant-time, static signals only.
pub(super) fn shift_to_employee_distance(
    solution: &HospitalPlan,
    shift: &Shift,
    employee_index: usize,
) -> f64 {
    let Some(employee) = solution.employees.get(employee_index) else {
        return f64::INFINITY;
    };
    let mut distance = 10.0 * hub_distance(solution, shift.hub, employee.home_hub);
    if employee
        .unavailable_days
        .iter()
        .any(|day| shift.touches(*day))
    {
        distance += 2_000.0;
    }
    distance
}

pub(super) fn shift_to_shift_distance(solution: &HospitalPlan, left: &Shift, right: &Shift) -> f64 {
    10.0 * hub_distance(solution, left.hub, right.hub)
        + start_band(left.start).abs_diff(start_band(right.start)).min(2) as f64
        + left.first_day.abs_diff(right.first_day).min(14) as f64
}

fn hub_distance(solution: &HospitalPlan, left: usize, right: usize) -> f64 {
    match (solution.hub_positions.get(left), solution.hub_positions.get(right)) {
        (Some((lx, ly)), Some((rx, ry))) => ((lx - rx).abs() + (ly - ry).abs()) as f64,
        _ => 8.0,
    }
}

fn start_band(start: i64) -> u32 {
    match (start % MINUTES_PER_DAY) / 60 {
        0..=7 => 0,
        8..=12 => 1,
        13..=17 => 2,
        _ => 3,
    }
}
