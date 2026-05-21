use std::sync::Arc;

use solverforge::cvrp::{ProblemData, VrpSolution};
use solverforge::prelude::*;
use solverforge::SolverConfig;

#[cfg(test)]
#[path = "domain_tests.rs"]
mod tests;

#[problem_fact]
pub struct Customer {
    #[planning_id]
    pub id: usize,
}

#[planning_entity]
pub struct Route {
    #[planning_id]
    pub id: usize,

    #[planning_list_variable(
        element_collection = "customer_values",
        solution_trait = "solverforge::cvrp::VrpSolution",
        distance_meter = "solverforge::cvrp::MatrixDistanceMeter",
        intra_distance_meter = "solverforge::cvrp::MatrixIntraDistanceMeter",
        route_get_fn = "solverforge::cvrp::get_route",
        route_set_fn = "solverforge::cvrp::replace_route",
        route_depot_fn = "solverforge::cvrp::depot_for_entity",
        route_metric_class_fn = "solverforge::cvrp::route_metric_class",
        route_distance_fn = "solverforge::cvrp::route_distance",
        route_feasible_fn = "solverforge::cvrp::route_feasible"
    )]
    pub visits: Vec<usize>,

    pub data_addr: usize,
}

impl Route {
    fn problem_data(&self) -> &ProblemData {
        assert!(
            self.data_addr != 0,
            "Route::data_addr must be initialized before solving"
        );
        // SAFETY: every Route gets its pointer from the owning CvrpPlan::shared Arc,
        // which is retained for the lifetime of the plan during each solve call.
        unsafe { &*(self.data_addr as *const ProblemData) }
    }

    pub fn is_empty(&self) -> bool {
        self.visits.is_empty()
    }

    pub fn load(&self) -> i64 {
        self.visits
            .iter()
            .map(|&node_idx| self.problem_data().demands[node_idx] as i64)
            .sum()
    }

    pub fn overload(&self) -> i64 {
        (self.load() - self.problem_data().capacity).max(0)
    }

    pub fn total_distance(&self) -> i64 {
        if self.visits.is_empty() {
            return 0;
        }

        let data = self.problem_data();
        let mut total = 0;
        let mut previous = data.depot;

        for &node_idx in &self.visits {
            total += data.distance_matrix[previous][node_idx];
            previous = node_idx;
        }

        total + data.distance_matrix[previous][data.depot]
    }

    pub fn materialized_route(&self) -> Vec<usize> {
        self.visits.clone()
    }
}

#[planning_solution(
    constraints = "crate::constraints::define_constraints",
    config = "crate::domain::solver_config_for_plan",
    solver_toml = "../solver.toml"
)]
pub struct CvrpPlan {
    #[problem_fact_collection]
    pub customers: Vec<Customer>,

    #[planning_list_element_collection(owner = "routes")]
    pub customer_values: Vec<usize>,

    #[planning_entity_collection]
    pub routes: Vec<Route>,

    #[planning_score]
    pub score: Option<HardSoftScore>,

    pub shared: Arc<ProblemData>,
    pub time_limit_secs: u64,
}

impl VrpSolution for CvrpPlan {
    fn vehicle_data_ptr(&self, _entity_idx: usize) -> *const ProblemData {
        Arc::as_ptr(&self.shared)
    }

    fn vehicle_visits(&self, entity_idx: usize) -> &[usize] {
        &self.routes[entity_idx].visits
    }

    fn vehicle_visits_mut(&mut self, entity_idx: usize) -> &mut Vec<usize> {
        &mut self.routes[entity_idx].visits
    }

    fn vehicle_count(&self) -> usize {
        self.routes.len()
    }
}

impl CvrpPlan {
    pub fn total_cost(&self) -> i64 {
        self.routes.iter().map(Route::total_distance).sum()
    }

    pub fn materialized_routes(&self) -> Vec<Vec<usize>> {
        self.routes
            .iter()
            .filter(|route| !route.is_empty())
            .map(Route::materialized_route)
            .collect()
    }
}

pub fn solver_config_for_plan(plan: &CvrpPlan, base_config: SolverConfig) -> SolverConfig {
    let mut config = base_config;
    let mut termination = config.termination.unwrap_or_default();
    termination.minutes_spent_limit = None;
    termination.seconds_spent_limit = Some(plan.time_limit_secs.max(1));
    config.termination = Some(termination);
    config
}
