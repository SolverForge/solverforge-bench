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

    let problem_data = Box::new(ProblemData {
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
    });
    let data_ptr: *const ProblemData = &*problem_data;

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
                data: data_ptr,
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
        data: data_ptr,
    };

    let solved = solve(plan, time_limit)?;

    let score = solved
        .score
        .ok_or_else(|| "SolverForge NRP produced no score".to_string())?;
    if score.hard() < 0 {
        return Err(format!(
            "SolverForge NRP produced no hard-feasible solution: {} hard score debt",
            -score.hard()
        ));
    }

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
        "cost": -score.soft(),
        "hard_violations": -score.hard(),
    });

    // Keep problem_data alive until after we've read from it
    drop(problem_data);

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
