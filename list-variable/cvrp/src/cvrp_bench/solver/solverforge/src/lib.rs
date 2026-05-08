#![allow(
    clippy::useless_conversion,
    reason = "pyo3 0.22 pyfunction expansion emits this false positive for PyResult"
)]

mod constraints;
mod domain;

#[cfg(test)]
#[path = "lib_tests.rs"]
mod tests;

use std::sync::Arc;

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use solverforge::cvrp::ProblemData;
use solverforge::{SolverEvent, SolverManager};

use crate::domain::{Customer, CvrpPlan, Route};

static MANAGER: SolverManager<CvrpPlan> = SolverManager::new();

#[derive(Deserialize)]
struct InstanceInput {
    dimension: usize,
    capacity: i32,
    demand: Vec<i32>,
    depot: usize,
    distance_matrix: Vec<Vec<i64>>,
}

#[derive(Serialize)]
struct SolutionOutput {
    routes: Vec<Vec<usize>>,
    cost: i64,
}

fn build_plan(input: InstanceInput, time_limit_secs: u64) -> CvrpPlan {
    let customer_node_ids: Vec<usize> = (0..input.dimension)
        .filter(|&node_idx| node_idx != input.depot)
        .collect();
    let distance_matrix = input.distance_matrix;
    let travel_times = distance_matrix.clone();

    let shared = Arc::new(ProblemData {
        capacity: input.capacity as i64,
        depot: input.depot,
        demands: input.demand,
        distance_matrix,
        time_windows: vec![(0, i64::MAX); input.dimension],
        service_durations: vec![0; input.dimension],
        travel_times,
        vehicle_departure_time: 0,
    });
    let data_addr = Arc::as_ptr(&shared) as usize;

    let customers = customer_node_ids
        .iter()
        .copied()
        .map(|node_id| Customer { id: node_id })
        .collect();

    let routes = (0..customer_node_ids.len())
        .map(|id| Route {
            id,
            visits: Vec::new(),
            data_addr,
        })
        .collect();

    CvrpPlan {
        customers,
        customer_values: customer_node_ids,
        routes,
        score: None,
        shared,
        time_limit_secs,
    }
}

#[pyfunction]
fn solve_cvrp(instance_json: &str, time_limit: u64) -> PyResult<String> {
    let input: InstanceInput = serde_json::from_str(instance_json)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    let plan = build_plan(input, time_limit);
    let (job_id, mut receiver) = MANAGER
        .solve(plan)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

    let solved = loop {
        match receiver.blocking_recv() {
            Some(SolverEvent::Completed { solution, .. }) => break Ok(solution),
            Some(SolverEvent::Cancelled { metadata }) => {
                break Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
                    "SolverForge job {} was cancelled ({:?})",
                    metadata.job_id, metadata.terminal_reason
                )))
            }
            Some(SolverEvent::Failed { metadata, error }) => {
                break Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
                    "SolverForge job {} failed: {}",
                    metadata.job_id, error
                )))
            }
            Some(SolverEvent::Progress { .. })
            | Some(SolverEvent::BestSolution { .. })
            | Some(SolverEvent::PauseRequested { .. })
            | Some(SolverEvent::Paused { .. })
            | Some(SolverEvent::Resumed { .. }) => {}
            None => {
                break Err(pyo3::exceptions::PyRuntimeError::new_err(
                    "SolverForge event stream closed before a terminal event",
                ))
            }
        }
    };

    let delete_result = MANAGER.delete(job_id).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!(
            "failed to delete SolverForge job {}: {}",
            job_id, e
        ))
    });

    let solved = solved?;
    delete_result?;
    let routes = solved.materialized_routes();
    let cost = solved.total_cost();

    let output = SolutionOutput { routes, cost };
    serde_json::to_string(&output)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

#[pymodule]
fn solverforge_cvrp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_cvrp, m)?)?;
    Ok(())
}
