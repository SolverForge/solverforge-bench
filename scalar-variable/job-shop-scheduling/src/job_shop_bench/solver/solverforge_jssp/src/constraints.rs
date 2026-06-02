use solverforge::prelude::*;
use solverforge_core::ConstraintRef;

use crate::domain::{
    operation_duration, operation_job_successors, operation_machine_owner, JsspPlan,
};

pub fn define_constraints() -> impl ConstraintSet<JsspPlan, HardSoftScore> {
    (ListPrecedenceMakespanConstraint::new(
        ConstraintRef::new("", "jsspSchedule"),
        0,
        operation_count,
        operation_duration,
        operation_job_successors,
        machine_count,
        machine_len,
        machine_get,
    )
    .with_expected_owner(Some(operation_machine_owner)),)
}

fn operation_count(plan: &JsspPlan) -> usize {
    plan.operations.len()
}

fn machine_count(plan: &JsspPlan) -> usize {
    plan.machine_sequences.len()
}

fn machine_len(plan: &JsspPlan, machine_id: usize) -> usize {
    plan.machine_sequences
        .get(machine_id)
        .map_or(0, |machine| machine.operations.len())
}

fn machine_get(plan: &JsspPlan, machine_id: usize, pos: usize) -> Option<usize> {
    plan.machine_sequences
        .get(machine_id)?
        .operations
        .get(pos)
        .copied()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::{JsspOperation, MachineSequence};

    fn score_from_evaluator(plan: &JsspPlan) -> HardSoftScore {
        let evaluation = plan.evaluate_schedule();
        HardSoftScore::of(
            -(evaluation.hard_penalty as i64),
            -(evaluation.makespan as i64),
        )
    }

    fn plan(machine_sequences: Vec<Vec<usize>>) -> JsspPlan {
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
                JsspOperation {
                    id: 2,
                    job_id: 1,
                    op_index: 0,
                    machine_id: 1,
                    duration: 4,
                    successor_id: Some(3),
                },
                JsspOperation {
                    id: 3,
                    job_id: 1,
                    op_index: 1,
                    machine_id: 0,
                    duration: 1,
                    successor_id: None,
                },
            ],
            machine_sequences: machine_sequences
                .into_iter()
                .enumerate()
                .map(|(id, operations)| MachineSequence { id, operations })
                .collect(),
            score: None,
            num_jobs: 2,
            num_machines: 2,
            time_limit_secs: 1,
        }
    }

    #[test]
    fn stock_constraint_matches_legacy_evaluator_for_valid_schedule() {
        let plan = plan(vec![vec![0, 3], vec![2, 1]]);

        assert_eq!(
            define_constraints().evaluate_all(&plan),
            score_from_evaluator(&plan)
        );
    }

    #[test]
    fn stock_constraint_matches_legacy_evaluator_for_cycle_penalty() {
        let plan = plan(vec![vec![3, 0], vec![1, 2]]);

        assert_eq!(
            define_constraints().evaluate_all(&plan),
            score_from_evaluator(&plan)
        );
    }

    #[test]
    fn stock_constraint_matches_legacy_evaluator_for_assignment_penalties() {
        let plan = plan(vec![vec![0, 1], vec![1, 2]]);

        assert_eq!(
            define_constraints().evaluate_all(&plan),
            score_from_evaluator(&plan)
        );
    }

    #[test]
    fn stock_constraint_updates_machine_route_incrementally() {
        let mut constraints = define_constraints();
        let mut plan = plan(vec![vec![0, 3], vec![2, 1]]);

        let mut score = constraints.initialize_all(&plan);
        assert_eq!(score, score_from_evaluator(&plan));

        score = score + constraints.on_retract_all(&plan, 0, 0);
        plan.machine_sequences[0].operations = vec![3, 0];
        score = score + constraints.on_insert_all(&plan, 0, 0);

        assert_eq!(score, score_from_evaluator(&plan));
        assert_eq!(constraints.evaluate_all(&plan), score_from_evaluator(&plan));
    }
}
