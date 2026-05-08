use std::sync::Arc;

use super::*;

fn sample_plan(time_limit_secs: u64) -> CvrpPlan {
    let distance_matrix = vec![vec![0, 5, 7], vec![5, 0, 11], vec![7, 11, 0]];
    let shared = Arc::new(ProblemData {
        capacity: 4,
        depot: 0,
        demands: vec![0, 2, 3],
        distance_matrix: distance_matrix.clone(),
        time_windows: vec![(0, i64::MAX); 3],
        service_durations: vec![0; 3],
        travel_times: distance_matrix,
        vehicle_departure_time: 0,
    });
    let data_addr = Arc::as_ptr(&shared) as usize;

    CvrpPlan {
        customers: vec![Customer { id: 1 }, Customer { id: 2 }],
        customer_values: vec![1, 2],
        routes: vec![
            Route {
                id: 0,
                visits: vec![1, 2],
                data_addr,
            },
            Route {
                id: 1,
                visits: Vec::new(),
                data_addr,
            },
        ],
        score: None,
        shared,
        time_limit_secs,
    }
}

#[test]
fn solver_config_for_plan_overlays_base_termination() {
    let base_config = SolverConfig::from_toml_str(include_str!("../solver.toml")).unwrap();
    let plan = sample_plan(7);

    let config = solver_config_for_plan(&plan, base_config.clone());

    assert_eq!(config.environment_mode, base_config.environment_mode);
    assert_eq!(config.random_seed, base_config.random_seed);
    assert_eq!(config.phases.len(), base_config.phases.len());
    assert_eq!(
        config
            .termination
            .as_ref()
            .and_then(|t| t.seconds_spent_limit),
        Some(7)
    );
    assert_eq!(
        config
            .termination
            .as_ref()
            .and_then(|t| t.minutes_spent_limit),
        None
    );
}

#[test]
fn cvrp_plan_materializes_only_non_empty_routes() {
    let plan = sample_plan(5);

    assert_eq!(plan.total_cost(), 23);
    assert_eq!(plan.materialized_routes(), vec![vec![1, 2]]);
}
