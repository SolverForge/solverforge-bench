use std::sync::OnceLock;

use solverforge::{SolverEvent, SolverManager};

use crate::domain::NrpPlan;

static MANAGER: OnceLock<SolverManager<NrpPlan>> = OnceLock::new();

pub fn solve(plan: NrpPlan, time_limit_secs: u64) -> Result<NrpPlan, String> {
    if plan.shifts.is_empty() {
        return Ok(plan);
    }

    let manager = MANAGER.get_or_init(SolverManager::new);
    let (job_id, mut rx) = manager
        .solve(plan)
        .map_err(|e| format!("SolverForge manager rejected NRP job: {e}"))?;

    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_time()
        .build()
        .map_err(|e| format!("Failed to create tokio runtime: {e}"))?;

    let deadline =
        std::time::Instant::now() + std::time::Duration::from_secs(time_limit_secs.max(1));
    let mut best = None;
    let mut failure = None;
    rt.block_on(async {
        let mut cancel_requested = false;
        loop {
            let remaining = deadline.saturating_duration_since(std::time::Instant::now());
            if remaining.is_zero() && !cancel_requested {
                let _ = manager.cancel(job_id);
                cancel_requested = true;
            }
            let wait_for = if cancel_requested {
                std::time::Duration::from_secs(10)
            } else {
                remaining.max(std::time::Duration::from_millis(100))
            };

            match tokio::time::timeout(wait_for, rx.recv()).await {
                Ok(Some(SolverEvent::BestSolution { solution, .. })) => best = Some(solution),
                Ok(Some(SolverEvent::Completed { solution, .. })) => {
                    best = Some(solution);
                    break;
                }
                Ok(Some(SolverEvent::Cancelled { .. })) => break,
                Ok(Some(SolverEvent::Failed { error, .. })) => {
                    failure = Some(format!("SolverForge NRP job failed: {error}"));
                    break;
                }
                Ok(Some(SolverEvent::Progress { .. }))
                | Ok(Some(SolverEvent::PauseRequested { .. }))
                | Ok(Some(SolverEvent::Paused { .. }))
                | Ok(Some(SolverEvent::Resumed { .. })) => {}
                Ok(None) => break,
                Err(_) => {
                    if cancel_requested {
                        failure =
                            Some("SolverForge NRP job did not stop after cancellation".to_string());
                        break;
                    }
                    let _ = manager.cancel(job_id);
                    cancel_requested = true;
                }
            }
        }
    });
    let _ = manager.delete(job_id);
    if let Some(error) = failure {
        return Err(error);
    }
    best.ok_or_else(|| "SolverForge NRP job produced no solution".to_string())
}
