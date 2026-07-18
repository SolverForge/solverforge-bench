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
    let mut operations: Vec<_> = input
        .operations
        .into_iter()
        .enumerate()
        .map(|(id, operation)| JsspOperation {
            id,
            job_id: operation.job_id,
            op_index: operation.op_index,
            machine_id: operation.machine_id,
            duration: operation.duration,
            successor_id: None,
        })
        .collect();
    let index_by_job_op = operations
        .iter()
        .map(|operation| ((operation.job_id, operation.op_index), operation.id))
        .collect::<std::collections::HashMap<_, _>>();
    for operation in &mut operations {
        operation.successor_id = index_by_job_op
            .get(&(operation.job_id, operation.op_index + 1))
            .copied();
    }
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
    let mut completed = None;
    let mut failure = None;

    while let Some(event) = receiver.blocking_recv() {
        match event {
            SolverEvent::BestSolution { .. } => {}
            SolverEvent::Completed { solution, .. } => {
                completed = Some(solution);
                break;
            }
            SolverEvent::Cancelled { .. } => {
                failure = Some("SolverForge JSSP job was cancelled".to_string());
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
    completed.ok_or_else(|| "SolverForge JSSP event stream closed before completion".to_string())
}

fn solution_output(
    plan: JsspPlan,
    fair_start_witness: FairStartWitness,
) -> Result<SolutionOutput, String> {
    let evaluation = plan.evaluate_schedule();
    if evaluation.hard_penalty > 0 {
        return Err(format!(
            "SolverForge JSSP returned an incomplete or invalid schedule (hard penalty: {})",
            evaluation.hard_penalty
        ));
    }
    let mut operations: Vec<OperationOutput> = plan
        .operations
        .iter()
        .map(|operation| -> Result<OperationOutput, String> {
            let start = evaluation
                .starts
                .get(operation.id)
                .and_then(|start| *start)
                .ok_or_else(|| {
                    format!(
                        "SolverForge JSSP did not compute a start for operation {}",
                        operation.id
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
        .collect::<Result<_, _>>()?;
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

#[cfg(test)]
mod tests {
    use super::*;

    fn plan(machine_operations: [Vec<usize>; 2]) -> JsspPlan {
        JsspPlan {
            operations: vec![
                JsspOperation {
                    id: 0,
                    job_id: 0,
                    op_index: 0,
                    machine_id: 0,
                    duration: 3,
                    successor_id: Some(1),
                },
                JsspOperation {
                    id: 1,
                    job_id: 0,
                    op_index: 1,
                    machine_id: 1,
                    duration: 2,
                    successor_id: None,
                },
            ],
            machine_sequences: machine_operations
                .into_iter()
                .enumerate()
                .map(|(id, operations)| MachineSequence { id, operations })
                .collect(),
            score: None,
            num_jobs: 1,
            num_machines: 2,
            time_limit_secs: 1,
        }
    }

    fn witness() -> FairStartWitness {
        FairStartWitness {
            adapter_hint_count: 0,
            preliminary_solve_count: 0,
            fallback_solution_enabled: false,
            preassigned_scalar_variables: 0,
            prefilled_list_variables: 0,
        }
    }

    #[test]
    fn solution_output_accepts_complete_schedule() {
        let output = solution_output(plan([vec![0], vec![1]]), witness())
            .expect("complete schedule should serialize");

        assert_eq!(output.operations.len(), 2);
        assert_eq!(output.reported_makespan, 5);
    }

    #[test]
    fn solution_output_rejects_missing_operation() {
        let result = solution_output(plan([vec![0], vec![]]), witness());

        assert!(matches!(result, Err(error) if error.contains("hard penalty")));
    }
}
