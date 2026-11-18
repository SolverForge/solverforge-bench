use std::sync::OnceLock;

use solverforge::{SolverEvent, SolverManager, SolverTelemetry};

use crate::domain::DeliveryPlan;

static MANAGER: OnceLock<SolverManager<DeliveryPlan>> = OnceLock::new();

pub fn solve(plan: DeliveryPlan) -> Result<(DeliveryPlan, Option<SolverTelemetry>), String> {
    if plan.deliveries.is_empty() {
        return Ok((plan, None));
    }

    let manager = MANAGER.get_or_init(SolverManager::new);
    let (job_id, mut rx) = manager
        .solve(plan)
        .map_err(|e| format!("SolverForge manager rejected delivery-scale job: {e}"))?;

    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|e| format!("Failed to create async runtime: {e}"))?;

    let mut completed = None;
    let mut telemetry = None;
    let mut failure = None;
    rt.block_on(async {
        loop {
            match rx.recv().await {
                Some(SolverEvent::BestSolution { metadata, .. }) => {
                    telemetry = Some(metadata.telemetry);
                }
                Some(SolverEvent::Completed { metadata, solution }) => {
                    telemetry = Some(metadata.telemetry);
                    completed = Some(solution);
                    break;
                }
                Some(SolverEvent::Cancelled { metadata }) => {
                    telemetry = Some(metadata.telemetry);
                    failure = Some("SolverForge delivery-scale job was cancelled".to_string());
                    break;
                }
                Some(SolverEvent::Failed { metadata, error }) => {
                    telemetry = Some(metadata.telemetry);
                    failure = Some(format!("SolverForge delivery-scale job failed: {error}"));
                    break;
                }
                Some(SolverEvent::Progress { metadata })
                | Some(SolverEvent::PauseRequested { metadata })
                | Some(SolverEvent::Paused { metadata })
                | Some(SolverEvent::Resumed { metadata }) => {
                    telemetry = Some(metadata.telemetry);
                }
                None => {
                    failure = Some(
                        "SolverForge delivery-scale event stream closed before completion"
                            .to_string(),
                    );
                    break;
                }
            }
        }
    });
    let _ = manager.delete(job_id);
    if let Some(error) = failure {
        return Err(error);
    }
    completed
        .map(|solution| (solution, telemetry))
        .ok_or_else(|| "SolverForge delivery-scale job produced no solution".to_string())
}
