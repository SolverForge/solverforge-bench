//! PyO3 entry point for the delivery-at-scale benchmark: reads the shared
//! solver-input document, builds the stock routing matrices from coordinates,
//! solves with SolverForge, and returns routes, scores, telemetry and the
//! fair-start witness.

use std::sync::Arc;

use pyo3::prelude::*;
use serde::Deserialize;
use solverforge::cvrp::ProblemData;
use solverforge::{Analyzable, SolverTelemetry};

use crate::solver::solve;
use crate::{Delivery, DeliveryPlan, Vehicle};

#[derive(Deserialize)]
struct InstanceInput {
    speed_mps: f64,
    depot: (i64, i64),
    departure_time: i64,
    vehicle_count: usize,
    capacity: i64,
    xs: Vec<i64>,
    ys: Vec<i64>,
    demands: Vec<i32>,
    min_starts: Vec<i64>,
    max_ends: Vec<i64>,
    services: Vec<i64>,
}

/// Euclidean distance over the speed, rounded half up to whole seconds; the
/// same integer rule as the validator and the Timefold model.
fn travel_seconds(ax: i64, ay: i64, bx: i64, by: i64, speed_mps: f64) -> i64 {
    let dx = ax - bx;
    let dy = ay - by;
    (((dx * dx + dy * dy) as f64).sqrt() / speed_mps + 0.5).floor() as i64
}

fn build_plan(input: InstanceInput, time_limit: u64) -> Result<DeliveryPlan, String> {
    let n = input.xs.len();
    for (name, len) in [
        ("ys", input.ys.len()),
        ("demands", input.demands.len()),
        ("min_starts", input.min_starts.len()),
        ("max_ends", input.max_ends.len()),
        ("services", input.services.len()),
    ] {
        if len != n {
            return Err(format!("{name} has {len} entries for {n} deliveries"));
        }
    }
    // Locations 0..n are deliveries; location n is the depot.
    let mut xs = input.xs;
    let mut ys = input.ys;
    xs.push(input.depot.0);
    ys.push(input.depot.1);
    let travel_times: Vec<Vec<i64>> = (0..=n)
        .map(|from| {
            (0..=n)
                .map(|to| travel_seconds(xs[from], ys[from], xs[to], ys[to], input.speed_mps))
                .collect()
        })
        .collect();
    let distance_matrix = travel_times.clone();

    let mut demands = input.demands;
    demands.push(0);
    let mut time_windows: Vec<(i64, i64)> = input
        .min_starts
        .iter()
        .copied()
        .zip(input.max_ends.iter().copied())
        .collect();
    time_windows.push((0, i64::MAX));
    let mut service_durations = input.services;
    service_durations.push(0);

    let shared = Arc::new(ProblemData {
        capacity: input.capacity,
        depot: n,
        demands,
        distance_matrix,
        time_windows,
        service_durations,
        travel_times,
        vehicle_departure_time: input.departure_time,
    });
    Ok(DeliveryPlan {
        deliveries: (0..n).map(|id| Delivery { id }).collect(),
        vehicles: (0..input.vehicle_count)
            .map(|id| Vehicle {
                id,
                delivery_order: Vec::new(),
                route_capacity_overage: 0,
                route_travel_seconds: 0,
                route_time_window_violation_seconds: 0,
            })
            .collect(),
        score: None,
        shared,
        time_limit_secs: time_limit.max(1),
    })
}

fn do_solve(instance_json: &str, time_limit: u64) -> Result<String, String> {
    let input: InstanceInput =
        serde_json::from_str(instance_json).map_err(|e| format!("Invalid JSON: {e}"))?;
    let plan = build_plan(input, time_limit)?;

    let fair_start_witness = serde_json::json!({
        "adapter_hint_count": 0,
        "preliminary_solve_count": 0,
        "fallback_solution_enabled": false,
        "preassigned_scalar_variables": 0,
        "prefilled_list_variables": plan.vehicles.iter().filter(|vehicle| !vehicle.delivery_order.is_empty()).count(),
    });

    let (solved, telemetry) = solve(plan)?;

    let score = solved
        .score
        .ok_or_else(|| "SolverForge delivery-scale produced no score".to_string())?;
    let analysis = solved.analyze();
    let fresh_score = analysis.score;
    let constraint_breakdown: Vec<_> = analysis
        .constraints
        .iter()
        .map(|constraint| {
            serde_json::json!({
                "name": &constraint.name,
                "score": constraint.score.to_string(),
                "match_count": constraint.match_count,
            })
        })
        .collect();
    let routes: Vec<&Vec<usize>> = solved
        .vehicles
        .iter()
        .map(|vehicle| &vehicle.delivery_order)
        .collect();

    let output = serde_json::json!({
        "routes": routes,
        "reported_cost": -score.soft(),
        "fresh_cost": -fresh_score.soft(),
        "hard_violations": -fresh_score.hard(),
        "reported_score": score.to_string(),
        "fresh_score": fresh_score.to_string(),
        "solverforge_telemetry": telemetry.as_ref().map(telemetry_json),
        "constraint_breakdown": constraint_breakdown,
        "fair_start_witness": fair_start_witness,
    });
    serde_json::to_string(&output).map_err(|e| format!("Serialization error: {e}"))
}

#[pyfunction]
fn solve_deliveries(instance_json: &str, time_limit: u64) -> PyResult<String> {
    do_solve(instance_json, time_limit).map_err(pyo3::exceptions::PyValueError::new_err)
}

#[pymodule]
fn solverforge_delivery_scale(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_deliveries, m)?)?;
    Ok(())
}

/// The `solverforge_telemetry` section of the output document.
fn telemetry_json(telemetry: &SolverTelemetry) -> serde_json::Value {
    serde_json::json!({
        "elapsed_ms": telemetry.elapsed.as_millis(),
        "step_count": telemetry.step_count,
        "moves_generated": telemetry.moves_generated,
        "moves_evaluated": telemetry.moves_evaluated,
        "moves_accepted": telemetry.moves_accepted,
        "moves_applied": telemetry.moves_applied,
        "score_calculations": telemetry.score_calculations,
        "generation_time_ms": telemetry.generation_time.as_millis(),
        "evaluation_time_ms": telemetry.evaluation_time.as_millis(),
        "phases": telemetry.phases.iter().map(|phase| serde_json::json!({
            "phase_type": phase.phase_type,
            "elapsed_ms": phase.elapsed.as_millis(),
            "step_count": phase.step_count,
            "moves_evaluated": phase.moves_evaluated,
            "generation_time_ms": phase.generation_time.as_millis(),
            "evaluation_time_ms": phase.evaluation_time.as_millis(),
        })).collect::<Vec<_>>(),
    })
}
