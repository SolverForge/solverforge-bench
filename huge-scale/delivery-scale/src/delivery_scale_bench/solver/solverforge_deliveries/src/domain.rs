use std::sync::Arc;

use solverforge::cvrp::{ProblemData, VrpSolution};
use solverforge::prelude::*;

/// A delivery stop: a problem fact placed by index into vehicle routes.
#[problem_fact]
pub struct Delivery {
    #[planning_id]
    pub id: usize,
}

/// A vehicle owning one route; the route is the list planning variable.
#[planning_entity]
pub struct Vehicle {
    #[planning_id]
    pub id: usize,
    #[planning_list_variable(
        element_collection = "deliveries",
        solution_trait = "solverforge::cvrp::VrpSolution",
        distance_meter = "solverforge::cvrp::MatrixDistanceMeter",
        intra_distance_meter = "solverforge::cvrp::MatrixIntraDistanceMeter",
        route_hooks = "solverforge::cvrp::route_hooks",
        savings_hooks = "crate::domain::strict_savings_hooks",
        savings_metric_class_fn = "solverforge::cvrp::savings_metric_class"
    )]
    pub delivery_order: Vec<usize>,
    #[cascading_update_shadow_variable]
    pub route_capacity_overage: i64,
    #[cascading_update_shadow_variable]
    pub route_travel_seconds: i64,
    #[cascading_update_shadow_variable]
    pub route_time_window_violation_seconds: i64,
}

#[planning_solution(
    constraints = "crate::constraints::define_constraints",
    config = "crate::domain::solver_config_for_plan",
    solver_toml = "../solver.toml"
)]
#[shadow_variable_updates(
    list_owner = "vehicles",
    post_update_listener = "refresh_vehicle_route_shadows"
)]
pub struct DeliveryPlan {
    #[problem_fact_collection]
    pub deliveries: Vec<Delivery>,
    #[planning_entity_collection]
    pub vehicles: Vec<Vehicle>,
    #[planning_score]
    pub score: Option<HardSoftScore>,
    /// One shared stop-to-stop matrix set for every vehicle (single depot).
    pub shared: Arc<ProblemData>,
    pub time_limit_secs: u64,
}

impl DeliveryPlan {
    /// List-variable post-update hook: recompute one route's shadow totals.
    pub fn refresh_vehicle_route_shadows(&mut self, vehicle_idx: usize) {
        let data = Arc::clone(&self.shared);
        if let Some(vehicle) = self.vehicles.get_mut(vehicle_idx) {
            let metrics = route_metrics(&data, &vehicle.delivery_order);
            vehicle.route_capacity_overage = metrics.capacity_overage;
            vehicle.route_travel_seconds = metrics.travel_seconds;
            vehicle.route_time_window_violation_seconds = metrics.time_window_violation_seconds;
        }
    }
}

pub struct RouteMetrics {
    pub capacity_overage: i64,
    pub travel_seconds: i64,
    pub time_window_violation_seconds: i64,
}

/// Route totals under the solverforge-deliveries rules: waiting before
/// `min_start`, lateness when service ends after `max_end`, and travel from the
/// depot through every stop back to the depot.
pub fn route_metrics(data: &ProblemData, route: &[usize]) -> RouteMetrics {
    if route.is_empty() {
        return RouteMetrics {
            capacity_overage: 0,
            travel_seconds: 0,
            time_window_violation_seconds: 0,
        };
    }
    let mut load = 0_i64;
    let mut travel = 0_i64;
    let mut lateness = 0_i64;
    let mut clock = data.vehicle_departure_time;
    let mut previous = data.depot;
    for &stop in route {
        load += i64::from(data.demands[stop]);
        let leg = data.travel_times[previous][stop];
        travel += leg;
        clock += leg;
        let (min_start, max_end) = data.time_windows[stop];
        clock = clock.max(min_start) + data.service_durations[stop];
        lateness += (clock - max_end).max(0);
        previous = stop;
    }
    travel += data.travel_times[previous][data.depot];
    RouteMetrics {
        capacity_overage: (load - data.capacity).max(0),
        travel_seconds: travel,
        time_window_violation_seconds: lateness,
    }
}

impl VrpSolution for DeliveryPlan {
    fn vehicle_data(&self, entity_idx: usize) -> Option<&ProblemData> {
        self.vehicles.get(entity_idx).map(|_| self.shared.as_ref())
    }

    fn vehicle_visits(&self, entity_idx: usize) -> &[usize] {
        &self.vehicles[entity_idx].delivery_order
    }

    fn vehicle_visits_mut(&mut self, entity_idx: usize) -> &mut Vec<usize> {
        &mut self.vehicles[entity_idx].delivery_order
    }

    fn vehicle_count(&self) -> usize {
        self.vehicles.len()
    }
}

pub fn solver_config_for_plan(
    plan: &DeliveryPlan,
    config: solverforge::SolverConfig,
) -> solverforge::SolverConfig {
    config.with_termination_seconds(plan.time_limit_secs.max(1))
}

/// Clarke-Wright hooks that reject a merge breaking capacity or a time window.
///
/// The stock `savings_hooks` bundle checks route structure only, so its merges
/// ignore capacity and time windows; `route_feasible` checks both.
pub mod strict_savings_hooks {
    use solverforge::cvrp::VrpSolution;

    pub fn depot<S: VrpSolution>(plan: &S, entity_idx: usize) -> usize {
        solverforge::cvrp::savings_depot_for_entity(plan, entity_idx)
    }

    pub fn distance<S: VrpSolution>(plan: &S, entity_idx: usize, from: usize, to: usize) -> i64 {
        solverforge::cvrp::savings_distance(plan, entity_idx, from, to)
    }

    pub fn feasible<S: VrpSolution>(plan: &S, entity_idx: usize, route: &[usize]) -> bool {
        solverforge::cvrp::route_feasible(plan, entity_idx, route)
    }
}
