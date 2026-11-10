//! PyO3 entry point for the CVRP benchmark: reads an instance as JSON, solves
//! it with SolverForge, and returns routes, telemetry and the fair-start witness.

use crate::{Customer, CvrpPlan, Route};
use std::collections::BTreeMap;
use std::sync::Arc;

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use solverforge::cvrp::ProblemData;
use solverforge::{PhaseTelemetry, SolverEvent, SolverManager, SolverTelemetry};

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
    fair_start_witness: FairStartWitness,
    solverforge_telemetry: TelemetryOutput,
}

/// Search counters the thread study reads to explain a cost difference.
#[derive(Serialize)]
struct TelemetryOutput {
    move_threads: usize,
    elapsed_ms: u128,
    step_count: u64,
    moves_generated: u64,
    moves_evaluated: u64,
    moves_speculative: u64,
    moves_applied: u64,
    generation_time_ms: u128,
    evaluation_time_ms: u128,
    phases: Vec<PhaseOutput>,
}

/// One phase's share of the run, so the study can read local search alone.
#[derive(Serialize)]
struct PhaseOutput {
    phase_type: String,
    elapsed_ms: u128,
    step_count: u64,
    moves_evaluated: u64,
    moves_speculative: u64,
    generation_time_ms: u128,
    evaluation_time_ms: u128,
}

impl PhaseOutput {
    fn new(phase: &PhaseTelemetry) -> Self {
        Self {
            phase_type: phase.phase_type.clone(),
            elapsed_ms: phase.elapsed.as_millis(),
            step_count: phase.step_count,
            moves_evaluated: phase.moves_evaluated,
            moves_speculative: phase.moves_speculative,
            generation_time_ms: phase.generation_time.as_millis(),
            evaluation_time_ms: phase.evaluation_time.as_millis(),
        }
    }
}

impl TelemetryOutput {
    fn new(move_threads: usize, telemetry: &SolverTelemetry) -> Self {
        Self {
            move_threads,
            elapsed_ms: telemetry.elapsed.as_millis(),
            step_count: telemetry.step_count,
            moves_generated: telemetry.moves_generated,
            moves_evaluated: telemetry.moves_evaluated,
            moves_speculative: telemetry.moves_speculative,
            moves_applied: telemetry.moves_applied,
            generation_time_ms: telemetry.generation_time.as_millis(),
            evaluation_time_ms: telemetry.evaluation_time.as_millis(),
            phases: telemetry.phases.iter().map(PhaseOutput::new).collect(),
        }
    }
}

#[derive(Serialize)]
struct FairStartWitness {
    adapter_hint_count: usize,
    preliminary_solve_count: usize,
    fallback_solution_enabled: bool,
    preassigned_scalar_variables: usize,
    prefilled_list_variables: usize,
}

fn build_plan(input: InstanceInput, time_limit_secs: u64, move_threads: usize) -> CvrpPlan {
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
        move_threads,
    }
}

fn ensure_complete_customer_assignment(plan: &CvrpPlan) -> Result<(), String> {
    let expected = plan.customer_values.iter().copied().fold(
        BTreeMap::<usize, usize>::new(),
        |mut counts, customer| {
            *counts.entry(customer).or_default() += 1;
            counts
        },
    );
    let assigned = plan
        .routes
        .iter()
        .flat_map(|route| &route.visits)
        .copied()
        .fold(BTreeMap::<usize, usize>::new(), |mut counts, customer| {
            *counts.entry(customer).or_default() += 1;
            counts
        });
    if assigned != expected {
        return Err(format!(
            "SolverForge CVRP returned an incomplete customer assignment: expected={expected:?}, assigned={assigned:?}"
        ));
    }
    Ok(())
}

#[pyfunction]
#[pyo3(signature = (instance_json, time_limit, move_threads = 1))]
fn solve_cvrp(instance_json: &str, time_limit: u64, move_threads: usize) -> PyResult<String> {
    let input: InstanceInput = serde_json::from_str(instance_json)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    let plan = build_plan(input, time_limit, move_threads);
    let fair_start_witness = FairStartWitness {
        adapter_hint_count: 0,
        preliminary_solve_count: 0,
        fallback_solution_enabled: false,
        preassigned_scalar_variables: 0,
        prefilled_list_variables: plan
            .routes
            .iter()
            .filter(|route| !route.visits.is_empty())
            .count(),
    };
    let (job_id, mut receiver) = MANAGER
        .solve(plan)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

    let solved = loop {
        match receiver.blocking_recv() {
            Some(SolverEvent::Completed { solution, metadata }) => {
                break Ok((solution, metadata.telemetry))
            }
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

    let (solved, telemetry) = solved?;
    delete_result?;
    ensure_complete_customer_assignment(&solved)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    let routes = solved.materialized_routes();
    let cost = solved.total_cost();

    let output = SolutionOutput {
        routes,
        cost,
        fair_start_witness,
        solverforge_telemetry: TelemetryOutput::new(move_threads, &telemetry),
    };
    serde_json::to_string(&output)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

#[pymodule]
fn solverforge_cvrp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_cvrp, m)?)?;
    Ok(())
}

#[cfg(test)]
#[path = "adapter_tests.rs"]
mod tests;
