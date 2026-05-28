mod constraints;

solverforge::planning_model! {
    root = "src";

    mod domain;

    pub use domain::JsspOperation;
    pub use domain::JsspPlan;
    pub use domain::MachineSequence;
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
    fair_start_witness: FairStartWitness,
}

#[derive(Serialize)]
struct FairStartWitness {
    adapter_hint_count: usize,
    preliminary_solve_count: usize,
    fallback_solution_enabled: bool,
    preassigned_scalar_variables: usize,
    prefilled_list_variables: usize,
}

fn build_plan(input: InstanceInput, time_limit_secs: u64) -> JsspPlan {
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
        })
        .collect();
    let machine_sequences = (0..input.num_machines)
        .map(|id| MachineSequence {
            id,
            operations: Vec::new(),
        })
        .collect();

    JsspPlan {
        operations,
        machine_sequences,
        score: None,
        num_jobs: input.num_jobs,
        num_machines: input.num_machines,
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

fn solution_output(
    plan: JsspPlan,
    fair_start_witness: FairStartWitness,
) -> Result<SolutionOutput, String> {
    let evaluation = plan.evaluate_schedule();
    let mut operations: Vec<OperationOutput> = plan
        .operations
        .iter()
        .map(|operation| {
            let start = evaluation.starts[operation.id].unwrap_or(0);
            OperationOutput {
                job_id: operation.job_id,
                op_index: operation.op_index,
                machine_id: operation.machine_id,
                start,
                duration: operation.duration,
            }
        })
        .collect();
    operations.sort_by_key(|operation| (operation.job_id, operation.op_index));
    Ok(SolutionOutput {
        operations,
        reported_makespan: evaluation.makespan,
        fair_start_witness,
    })
}

#[pyfunction]
fn solve_jssp(instance_json: &str, time_limit: u64) -> PyResult<String> {
    let input: InstanceInput = serde_json::from_str(instance_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
    let plan = build_plan(input, time_limit);
    let fair_start_witness = FairStartWitness {
        adapter_hint_count: 0,
        preliminary_solve_count: 0,
        fallback_solution_enabled: false,
        preassigned_scalar_variables: 0,
        prefilled_list_variables: plan
            .machine_sequences
            .iter()
            .filter(|machine| !machine.operations.is_empty())
            .count(),
    };
    let solved = solve_plan(plan).map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
    let output = solution_output(solved, fair_start_witness)
        .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
    serde_json::to_string(&output)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[pymodule]
fn solverforge_jssp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_jssp, m)?)?;
    Ok(())
}
