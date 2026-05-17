mod constraints;

solverforge::planning_model! {
    root = "src";

    mod domain;

    pub use domain::JsspOperation;
    pub use domain::JsspPlan;
    pub use domain::StartValue;
}

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use solverforge::{SolverEvent, SolverManager};

static MANAGER: SolverManager<JsspPlan> = SolverManager::new();

#[derive(Deserialize)]
struct OperationInput {
    job_id: usize,
    op_index: usize,
    machine_id: usize,
    duration: usize,
}

#[derive(Deserialize)]
struct InstanceInput {
    num_jobs: usize,
    num_machines: usize,
    operations: Vec<OperationInput>,
}

#[derive(Serialize)]
struct OperationOutput {
    job_id: usize,
    op_index: usize,
    machine_id: usize,
    start: usize,
    duration: usize,
}

#[derive(Serialize)]
struct SolutionOutput {
    operations: Vec<OperationOutput>,
    reported_makespan: usize,
}

fn dispatch_starts(input: &InstanceInput) -> Vec<usize> {
    let mut job_ready = vec![0; input.num_jobs];
    let mut machine_ready = vec![0; input.num_machines];
    input
        .operations
        .iter()
        .map(|operation| {
            let start = job_ready[operation.job_id].max(machine_ready[operation.machine_id]);
            let finish = start + operation.duration;
            job_ready[operation.job_id] = finish;
            machine_ready[operation.machine_id] = finish;
            start
        })
        .collect()
}

fn build_plan(input: InstanceInput, time_limit_secs: u64) -> JsspPlan {
    let horizon = input
        .operations
        .iter()
        .map(|operation| operation.duration)
        .sum::<usize>()
        .max(1);
    let starts = dispatch_starts(&input);
    let operations = input
        .operations
        .into_iter()
        .enumerate()
        .map(|(id, operation)| JsspOperation {
            id,
            job_id: operation.job_id,
            op_index: operation.op_index,
            machine_id: operation.machine_id,
            duration: operation.duration,
            start: Some(starts[id]),
        })
        .collect();

    JsspPlan {
        start_values: (0..=horizon).map(|id| StartValue { id }).collect(),
        operations,
        score: None,
        time_limit_secs,
    }
}

fn solve_plan(plan: JsspPlan) -> Result<JsspPlan, String> {
    let (job_id, mut receiver) = MANAGER
        .solve(plan)
        .map_err(|error| format!("SolverForge manager rejected JSSP job: {error}"))?;
    let mut best = None;
    let mut failure = None;

    while let Some(event) = receiver.blocking_recv() {
        match event {
            SolverEvent::BestSolution { solution, .. } => {
                best = Some(solution);
            }
            SolverEvent::Completed { solution, .. } => {
                best = Some(solution);
                break;
            }
            SolverEvent::Cancelled { .. } => {
                break;
            }
            SolverEvent::Failed { error, .. } => {
                failure = Some(format!("SolverForge JSSP job failed: {error}"));
                break;
            }
            SolverEvent::Progress { .. }
            | SolverEvent::PauseRequested { .. }
            | SolverEvent::Paused { .. }
            | SolverEvent::Resumed { .. } => {}
        }
    }
    let _ = MANAGER.delete(job_id);
    if let Some(error) = failure {
        return Err(error);
    }
    best.ok_or_else(|| "SolverForge JSSP job produced no solution".to_string())
}

fn solution_output(plan: JsspPlan) -> Result<SolutionOutput, String> {
    let mut operations: Vec<OperationOutput> = plan
        .operations
        .into_iter()
        .map(|operation| {
            let start = operation.start.ok_or_else(|| {
                format!(
                    "SolverForge returned an unassigned start for job {} operation {}",
                    operation.job_id, operation.op_index
                )
            })?;
            Ok(OperationOutput {
                job_id: operation.job_id,
                op_index: operation.op_index,
                machine_id: operation.machine_id,
                start,
                duration: operation.duration,
            })
        })
        .collect::<Result<_, String>>()?;
    operations.sort_by_key(|operation| (operation.job_id, operation.op_index));
    let reported_makespan = operations
        .iter()
        .map(|operation| operation.start + operation.duration)
        .max()
        .unwrap_or(0);
    Ok(SolutionOutput {
        operations,
        reported_makespan,
    })
}

#[pyfunction]
fn solve_jssp(instance_json: &str, time_limit: u64) -> PyResult<String> {
    let input: InstanceInput = serde_json::from_str(instance_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
    let plan = build_plan(input, time_limit);
    let solved = solve_plan(plan).map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
    let output = solution_output(solved).map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
    serde_json::to_string(&output)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[pymodule]
fn solverforge_jssp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_jssp, m)?)?;
    Ok(())
}
