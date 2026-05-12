use std::sync::OnceLock;

use solverforge::{SolverEvent, SolverManager, SolverTelemetry};

use crate::domain::NrpPlan;

static MANAGER: OnceLock<SolverManager<NrpPlan>> = OnceLock::new();

pub fn solve(
    plan: NrpPlan,
    _time_limit_secs: u64,
) -> Result<(NrpPlan, Option<SolverTelemetry>), String> {
    if plan.shifts.is_empty() {
        return Ok((plan, None));
    }

    let manager = MANAGER.get_or_init(SolverManager::new);
    let (job_id, mut rx) = manager
        .solve(plan)
        .map_err(|e| format!("SolverForge manager rejected NRP job: {e}"))?;

    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|e| format!("Failed to create async runtime: {e}"))?;

    let mut best = None;
    let mut telemetry = None;
    let mut failure = None;
    rt.block_on(async {
        loop {
            match rx.recv().await {
                Some(SolverEvent::BestSolution { metadata, solution }) => {
                    telemetry = Some(metadata.telemetry);
                    best = Some(solution);
                }
                Some(SolverEvent::Completed { metadata, solution }) => {
                    telemetry = Some(metadata.telemetry);
                    best = Some(solution);
                    break;
                }
                Some(SolverEvent::Cancelled { metadata }) => {
                    telemetry = Some(metadata.telemetry);
                    break;
                }
                Some(SolverEvent::Failed { metadata, error }) => {
                    telemetry = Some(metadata.telemetry);
                    failure = Some(format!("SolverForge NRP job failed: {error}"));
                    break;
                }
                Some(SolverEvent::Progress { metadata })
                | Some(SolverEvent::PauseRequested { metadata })
                | Some(SolverEvent::Paused { metadata })
                | Some(SolverEvent::Resumed { metadata }) => {
                    telemetry = Some(metadata.telemetry);
                }
                None => break,
            }
        }
    });
    let _ = manager.delete(job_id);
    if let Some(error) = failure {
        return Err(error);
    }
    best.map(|solution| (solution, telemetry))
        .ok_or_else(|| "SolverForge NRP job produced no solution".to_string())
}
