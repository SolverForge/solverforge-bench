mod constraints;

solverforge::planning_model! {
    root = "src";

    mod domain;

    pub use domain::ContractData;
    pub use domain::NrpPlan;
    pub use domain::NrpShift;
    pub use domain::NurseData;
    pub use domain::NurseHistoryData;
    pub use domain::NurseIndex;
    pub use domain::NurseShiftTypeIndex;
    pub use domain::ProblemData;
    pub use domain::ShiftTypeData;
}
mod solver;

use pyo3::prelude::*;
use serde::Deserialize;
use solverforge::Analyzable;

use solver::solve;

#[derive(Deserialize)]
struct NurseInput {
    id: String,
    contract_idx: usize,
    skills: Vec<usize>,
}

#[derive(Deserialize)]
struct ShiftInput {
    week: usize,
    day: usize,
    shift_type_idx: usize,
    skill_idx: usize,
    is_minimum: bool,
}

#[derive(Deserialize)]
struct ForbiddenInput {
    preceding: usize,
    succeeding: Vec<usize>,
}

#[derive(Deserialize)]
struct ShiftOffInput {
    nurse_idx: usize,
    global_day: usize,
    shift_type_idx: usize,
}

#[derive(Deserialize)]
struct HistoryInput {
    nurse_idx: usize,
    num_assignments: i64,
    num_working_weekends: i64,
    last_shift_type_idx: Option<usize>,
    num_consecutive_assignments: i64,
    num_consecutive_working: i64,
    num_consecutive_off: i64,
}

#[derive(Deserialize)]
struct InstanceInput {
    nurses: Vec<NurseInput>,
    contracts: Vec<ContractData>,
    shift_types: Vec<ShiftTypeData>,
    forbidden: Vec<ForbiddenInput>,
    shift_off_requests: Vec<ShiftOffInput>,
    nurse_history: Vec<HistoryInput>,
    shifts: Vec<ShiftInput>,
    num_weeks: usize,
    skill_names: Vec<String>,
    shift_type_names: Vec<String>,
    nurse_names: Vec<String>,
}

fn do_solve(instance_json: &str, time_limit: u64) -> Result<String, String> {
    let input: InstanceInput =
        serde_json::from_str(instance_json).map_err(|e| format!("Invalid JSON: {}", e))?;

    let num_shift_types = input.shift_types.len();
    let nurses: Vec<NurseData> = input
        .nurses
        .into_iter()
        .enumerate()
        .map(|(i, n)| NurseData {
            index: i,
            id: n.id,
            contract_idx: n.contract_idx,
            skills: n.skills,
        })
        .collect();

    let mut nurse_history_by_index: Vec<Option<NurseHistoryData>> = vec![None; nurses.len()];
    for h in input.nurse_history {
        if h.nurse_idx >= nurses.len() {
            return Err(format!(
                "Nurse history index {} is out of range",
                h.nurse_idx
            ));
        }
        nurse_history_by_index[h.nurse_idx] = Some(NurseHistoryData {
            nurse_idx: h.nurse_idx,
            num_assignments: h.num_assignments,
            num_working_weekends: h.num_working_weekends,
            last_shift_type_idx: h.last_shift_type_idx,
            num_consecutive_assignments: h.num_consecutive_assignments,
            num_consecutive_working: h.num_consecutive_working,
            num_consecutive_off: h.num_consecutive_off,
        });
    }
    let nurse_history: Vec<NurseHistoryData> = nurse_history_by_index
        .into_iter()
        .enumerate()
        .map(|(nurse_idx, history)| {
            history.ok_or_else(|| format!("Missing history for nurse index {}", nurse_idx))
        })
        .collect::<Result<_, _>>()?;

    let forbidden: Vec<(usize, Vec<usize>)> = input
        .forbidden
        .into_iter()
        .map(|f| (f.preceding, f.succeeding))
        .collect();

    let shift_off_requests: Vec<(usize, usize, usize)> = input
        .shift_off_requests
        .into_iter()
        .map(|s| (s.nurse_idx, s.global_day, s.shift_type_idx))
        .collect();
    let total_days = input.num_weeks * 7;
    let mut shift_off_requests_by_nurse_day = vec![vec![Vec::new(); total_days]; nurses.len()];
    for &(nurse_idx, global_day, shift_type_idx) in &shift_off_requests {
        if nurse_idx < shift_off_requests_by_nurse_day.len() && global_day < total_days {
            shift_off_requests_by_nurse_day[nurse_idx][global_day].push(shift_type_idx);
        }
    }

    let mut forbidden_successors = vec![Vec::new(); num_shift_types];
    for (preceding, succeeding) in &forbidden {
        if *preceding < forbidden_successors.len() {
            forbidden_successors[*preceding] = succeeding.clone();
        }
    }

    let problem_data = ProblemData {
        nurses,
        contracts: input.contracts,
        shift_types: input.shift_types,
        forbidden,
        forbidden_successors,
        shift_off_requests,
        shift_off_requests_by_nurse_day,
        nurse_history,
        num_weeks: input.num_weeks,
        num_shift_types,
    };
    let shifts: Vec<NrpShift> = input
        .shifts
        .into_iter()
        .enumerate()
        .map(|(id, s)| {
            let global_day = s.week * 7 + s.day;
            let shift_type_idx = s.shift_type_idx;
            let forbidden_predecessors = problem_data
                .forbidden
                .iter()
                .filter_map(|(preceding, succeeding)| {
                    if succeeding.contains(&shift_type_idx) {
                        Some(*preceding)
                    } else {
                        None
                    }
                })
                .collect();
            let shift_off_request_nurses = problem_data
                .shift_off_requests_by_nurse_day
                .iter()
                .enumerate()
                .flat_map(|(nurse_idx, days)| {
                    days.get(global_day).into_iter().flat_map(move |requests| {
                        requests.iter().filter_map(move |request_shift| {
                            (*request_shift == usize::MAX || *request_shift == shift_type_idx)
                                .then_some(nurse_idx)
                        })
                    })
                })
                .collect();

            NrpShift {
                forbidden_predecessors,
                shift_off_request_nurses,
                id,
                week: s.week,
                day: s.day,
                shift_type_idx,
                skill_idx: s.skill_idx,
                is_minimum: s.is_minimum,
                nurse_idx: None,
            }
        })
        .collect();

    let nurse_indices: Vec<NurseIndex> = problem_data
        .nurses
        .iter()
        .map(|nurse| {
            let contract = &problem_data.contracts[nurse.contract_idx];
            let history = &problem_data.nurse_history[nurse.index];

            NurseIndex {
                id: nurse.index,
                skills: nurse.skills.clone(),
                last_shift_type_idx: history.last_shift_type_idx,
                history_assignments: history.num_assignments,
                history_working_weekends: history.num_working_weekends,
                history_consecutive_assignments: history.num_consecutive_assignments,
                history_consecutive_working: history.num_consecutive_working,
                history_consecutive_off: history.num_consecutive_off,
                total_days: total_days as i64,
                min_assignments: contract.min_assignments,
                max_assignments: contract.max_assignments,
                min_consecutive_working: contract.min_consecutive_working,
                max_consecutive_working: contract.max_consecutive_working,
                min_consecutive_off: contract.min_consecutive_off,
                max_consecutive_off: contract.max_consecutive_off,
                max_working_weekends: contract.max_working_weekends,
                complete_weekends: contract.complete_weekends,
            }
        })
        .collect();
    let nurse_shift_type_indices: Vec<NurseShiftTypeIndex> =
        problem_data
            .nurses
            .iter()
            .flat_map(|nurse| {
                let history = &problem_data.nurse_history[nurse.index];
                problem_data.shift_types.iter().enumerate().map(
                    move |(shift_type_idx, shift_type)| NurseShiftTypeIndex {
                        id: nurse.index * num_shift_types + shift_type_idx,
                        nurse_idx: nurse.index,
                        shift_type_idx,
                        min_consecutive: shift_type.min_consecutive,
                        max_consecutive: shift_type.max_consecutive,
                        history_last_shift_type_idx: history.last_shift_type_idx,
                        history_consecutive_assignments: history.num_consecutive_assignments,
                        total_days: total_days as i64,
                    },
                )
            })
            .collect();

    let shift_nurse_candidates: Vec<Vec<usize>> = shifts
        .iter()
        .map(|shift| {
            problem_data
                .nurses
                .iter()
                .filter(|nurse| {
                    nurse.skills.contains(&shift.skill_idx)
                        && (shift.global_day() != 0
                            || problem_data.history_allows(nurse.index, shift.shift_type_idx))
                })
                .map(|nurse| nurse.index)
                .collect()
        })
        .collect();
    let shift_indices: Vec<usize> = (0..shifts.len()).collect();

    let plan = NrpPlan {
        shifts,
        nurse_indices,
        nurse_shift_type_indices,
        score: None,
        shift_nurse_candidates,
        shift_indices,
        time_limit_secs: time_limit.max(1),
        data: problem_data,
    };
    let fair_start_witness = serde_json::json!({
        "adapter_hint_count": 0,
        "preliminary_solve_count": 0,
        "fallback_solution_enabled": false,
        "preassigned_scalar_variables": plan.shifts.iter().filter(|shift| shift.nurse_idx.is_some()).count(),
        "prefilled_list_variables": 0,
    });

    let (solved, telemetry) = solve(plan, time_limit)?;

    let score = solved
        .score
        .ok_or_else(|| "SolverForge NRP produced no score".to_string())?;
    let analysis = solved.analyze();
    let fresh_score = analysis.score;
    let reported_cost = -score.soft();
    let fresh_cost = -fresh_score.soft();
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

    // Build output: assignments grouped by week
    let days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    let mut weekly: Vec<Vec<serde_json::Value>> = vec![vec![]; input.num_weeks];
    for s in &solved.shifts {
        if let Some(nurse_idx) = s.nurse_idx {
            let obj = serde_json::json!({
                "nurse": input.nurse_names[nurse_idx],
                "day": days[s.day],
                "shiftType": input.shift_type_names[s.shift_type_idx],
                "skill": input.skill_names[s.skill_idx],
            });
            weekly[s.week].push(obj);
        }
    }

    let output = serde_json::json!({
        "assignments": weekly,
        "cost": fresh_cost,
        "reported_cost": reported_cost,
        "fresh_cost": fresh_cost,
        "score_delta": reported_cost - fresh_cost,
        "score_drift": score != fresh_score,
        "hard_violations": -fresh_score.hard(),
        "reported_score": score.to_string(),
        "fresh_score": fresh_score.to_string(),
        "solverforge_telemetry": telemetry.as_ref().map(|telemetry| serde_json::json!({
            "step_count": telemetry.step_count,
            "moves_generated": telemetry.moves_generated,
            "moves_evaluated": telemetry.moves_evaluated,
            "moves_accepted": telemetry.moves_accepted,
            "moves_applied": telemetry.moves_applied,
            "moves_not_doable": telemetry.moves_not_doable,
            "moves_acceptor_rejected": telemetry.moves_acceptor_rejected,
            "moves_forager_ignored": telemetry.moves_forager_ignored,
            "moves_hard_improving": telemetry.moves_hard_improving,
            "moves_hard_neutral": telemetry.moves_hard_neutral,
            "moves_hard_worse": telemetry.moves_hard_worse,
            "score_calculations": telemetry.score_calculations,
            "scalar_assignment_required_remaining": telemetry.scalar_assignment_required_remaining,
            "selector_telemetry": telemetry.selector_telemetry.iter().map(|selector| serde_json::json!({
                "selector_index": selector.selector_index,
                "selector_label": selector.selector_label,
                "moves_generated": selector.moves_generated,
                "moves_evaluated": selector.moves_evaluated,
                "moves_accepted": selector.moves_accepted,
                "moves_applied": selector.moves_applied,
                "moves_not_doable": selector.moves_not_doable,
                "moves_acceptor_rejected": selector.moves_acceptor_rejected,
                "moves_forager_ignored": selector.moves_forager_ignored,
            })).collect::<Vec<_>>(),
            "move_telemetry": telemetry.move_telemetry.iter().map(|mov| serde_json::json!({
                "move_label": mov.move_label,
                "moves_generated": mov.moves_generated,
                "moves_evaluated": mov.moves_evaluated,
                "moves_accepted": mov.moves_accepted,
                "moves_applied": mov.moves_applied,
                "moves_not_doable": mov.moves_not_doable,
                "moves_acceptor_rejected": mov.moves_acceptor_rejected,
                "moves_forager_ignored": mov.moves_forager_ignored,
                "moves_score_improving": mov.moves_score_improving,
                "moves_score_equal": mov.moves_score_equal,
                "moves_score_worse": mov.moves_score_worse,
                "moves_rejected_improving": mov.moves_rejected_improving,
                "applied_score_improvement": mov.applied_score_improvement,
            })).collect::<Vec<_>>(),
            "applied_move_trace": telemetry.applied_move_trace.iter().map(|mov| serde_json::json!({
                "step_index": mov.step_index,
                "move_label": mov.move_label,
                "selected_candidate_index": mov.selected_candidate_index,
                "moves_generated_this_step": mov.moves_generated_this_step,
                "moves_evaluated_this_step": mov.moves_evaluated_this_step,
                "moves_accepted_this_step": mov.moves_accepted_this_step,
                "moves_forager_ignored_this_step": mov.moves_forager_ignored_this_step,
                "score_before": mov.score_before,
                "score_after": mov.score_after,
                "score_delta": mov.score_delta,
                "hard_feasible_before": mov.hard_feasible_before,
                "hard_feasible_after": mov.hard_feasible_after,
            })).collect::<Vec<_>>(),
        })),
        "constraint_breakdown": constraint_breakdown,
        "fair_start_witness": fair_start_witness,
    });

    serde_json::to_string(&output).map_err(|e| format!("Serialization error: {}", e))
}

#[pyfunction]
fn solve_nrp(instance_json: &str, time_limit: u64) -> PyResult<String> {
    do_solve(instance_json, time_limit).map_err(pyo3::exceptions::PyValueError::new_err)
}

#[pymodule]
fn solverforge_nrp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_nrp, m)?)?;
    Ok(())
}
