//! PyO3 entry point for the hospital-at-scale benchmark: reads the shared
//! solver-input document, solves it with SolverForge, and returns one
//! employee index per shift, scores, telemetry and the fair-start witness.

use crate::domain::MINUTES_PER_DAY;
use crate::solver::solve;
use crate::{Employee, HospitalPlan, Shift};
use pyo3::prelude::*;
use serde::Deserialize;
use solverforge::{Analyzable, SolverTelemetry};

/// Same-skill shifts on each side of a shift, in start order, offered to
/// nearby swap selection. Bounded so neighbourhoods stay constant-size.
const NEIGHBOURS_PER_SIDE: usize = 16;

#[derive(Deserialize)]
struct EmployeeInput {
    home_hub: usize,
    skills: Vec<usize>,
    unavailable_days: Vec<i64>,
    desired_days: Vec<i64>,
    undesired_days: Vec<i64>,
}

#[derive(Deserialize)]
struct ShiftInput {
    start: i64,
    end: i64,
    hub: usize,
    required_skill: usize,
}

#[derive(Deserialize)]
struct InstanceInput {
    hubs: Vec<(i64, i64)>,
    skill_hubs: Vec<usize>,
    skill_candidates: Vec<Vec<usize>>,
    employees: Vec<EmployeeInput>,
    shifts: Vec<ShiftInput>,
}

fn build_plan(input: InstanceInput, time_limit: u64) -> Result<HospitalPlan, String> {
    let skill_count = input.skill_hubs.len();
    if input.skill_candidates.len() != skill_count {
        return Err(format!(
            "skill_candidates covers {} skills, instance has {skill_count}",
            input.skill_candidates.len()
        ));
    }
    let employee_count = input.employees.len();
    if let Some(bad) = input
        .skill_candidates
        .iter()
        .flatten()
        .find(|employee| **employee >= employee_count)
    {
        return Err(format!("candidate employee {bad} is out of range"));
    }

    let employees: Vec<Employee> = input
        .employees
        .into_iter()
        .enumerate()
        .map(|(index, employee)| Employee {
            index,
            home_hub: employee.home_hub,
            skills: employee.skills,
            unavailable_days: employee.unavailable_days,
            desired_days: employee.desired_days,
            undesired_days: employee.undesired_days,
        })
        .collect();

    let mut shifts = Vec::with_capacity(input.shifts.len());
    for (index, shift) in input.shifts.into_iter().enumerate() {
        if shift.end <= shift.start {
            return Err(format!("shift {index} ends before it starts"));
        }
        if shift.required_skill >= skill_count {
            return Err(format!(
                "shift {index} requires unknown skill {}",
                shift.required_skill
            ));
        }
        shifts.push(Shift {
            index,
            start: shift.start,
            end: shift.end,
            first_day: shift.start.div_euclid(MINUTES_PER_DAY),
            last_day: (shift.end - 1).div_euclid(MINUTES_PER_DAY),
            hub: shift.hub,
            required_skill: shift.required_skill,
            employee_idx: None,
        });
    }

    let shift_neighbours = same_skill_neighbours(&shifts, skill_count);
    Ok(HospitalPlan {
        shifts,
        employees,
        score: None,
        skill_candidates: input.skill_candidates,
        shift_neighbours,
        hub_positions: input.hubs,
        time_limit_secs: time_limit.max(1),
    })
}

fn same_skill_neighbours(shifts: &[Shift], skill_count: usize) -> Vec<Vec<usize>> {
    let mut by_skill: Vec<Vec<usize>> = vec![Vec::new(); skill_count];
    for shift in shifts {
        by_skill[shift.required_skill].push(shift.index);
    }
    let mut neighbours = vec![Vec::new(); shifts.len()];
    for ordered in &mut by_skill {
        ordered.sort_by_key(|index| (shifts[*index].start, *index));
        for (position, shift_index) in ordered.iter().enumerate() {
            let low = position.saturating_sub(NEIGHBOURS_PER_SIDE);
            let high = (position + NEIGHBOURS_PER_SIDE + 1).min(ordered.len());
            neighbours[*shift_index] = ordered[low..high]
                .iter()
                .copied()
                .filter(|other| other != shift_index)
                .collect();
        }
    }
    neighbours
}

fn do_solve(instance_json: &str, time_limit: u64) -> Result<String, String> {
    let input: InstanceInput =
        serde_json::from_str(instance_json).map_err(|e| format!("Invalid JSON: {e}"))?;
    let plan = build_plan(input, time_limit)?;

    let fair_start_witness = serde_json::json!({
        "adapter_hint_count": 0,
        "preliminary_solve_count": 0,
        "fallback_solution_enabled": false,
        "preassigned_scalar_variables": plan.shifts.iter().filter(|shift| shift.employee_idx.is_some()).count(),
        "prefilled_list_variables": 0,
    });

    let (solved, telemetry) = solve(plan)?;

    let score = solved
        .score
        .ok_or_else(|| "SolverForge hospital-scale produced no score".to_string())?;
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
    let assignments: Vec<Option<usize>> = solved
        .shifts
        .iter()
        .map(|shift| shift.employee_idx)
        .collect();

    let output = serde_json::json!({
        "assignments": assignments,
        "reported_cost": -score.soft(),
        "fresh_cost": -fresh_score.soft(),
        "score_delta": fresh_score.soft() - score.soft(),
        "score_drift": score != fresh_score,
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
fn solve_hospital(instance_json: &str, time_limit: u64) -> PyResult<String> {
    do_solve(instance_json, time_limit).map_err(pyo3::exceptions::PyValueError::new_err)
}

#[pymodule]
fn solverforge_hospital_scale(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_hospital, m)?)?;
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
