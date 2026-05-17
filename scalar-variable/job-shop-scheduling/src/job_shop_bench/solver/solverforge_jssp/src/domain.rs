use solverforge::prelude::*;

#[problem_fact]
pub struct StartValue {
    #[planning_id]
    pub id: usize,
}

#[planning_entity]
pub struct JsspOperation {
    #[planning_id]
    pub id: usize,
    pub job_id: usize,
    pub op_index: usize,
    pub machine_id: usize,
    pub duration: usize,

    #[planning_variable(value_range_provider = "start_values", allows_unassigned = true)]
    pub start: Option<usize>,
}

impl JsspOperation {
    pub fn end(&self) -> Option<usize> {
        self.start.map(|start| start + self.duration)
    }
}

#[planning_solution(
    constraints = "crate::constraints::define_constraints",
    config = "crate::domain::solver_config_for_plan",
    solver_toml = "../solver.toml"
)]
pub struct JsspPlan {
    #[problem_fact_collection]
    pub start_values: Vec<StartValue>,

    #[planning_entity_collection]
    pub operations: Vec<JsspOperation>,

    #[planning_score]
    pub score: Option<HardSoftScore>,

    pub time_limit_secs: u64,
}

impl JsspPlan {
    pub fn reported_makespan(&self) -> usize {
        self.operations
            .iter()
            .filter_map(JsspOperation::end)
            .max()
            .unwrap_or(0)
    }
}

pub fn solver_config_for_plan(
    plan: &JsspPlan,
    config: solverforge::SolverConfig,
) -> solverforge::SolverConfig {
    config.with_termination_seconds(plan.time_limit_secs.max(1))
}
