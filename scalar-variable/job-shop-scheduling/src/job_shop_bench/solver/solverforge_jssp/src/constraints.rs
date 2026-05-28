use solverforge::prelude::*;
use solverforge_core::ConstraintRef;
use solverforge_scoring::{ConstraintAnalysis, ConstraintResult};

use crate::domain::JsspPlan;

pub fn define_constraints() -> impl ConstraintSet<JsspPlan, HardSoftScore> {
    (JsspScoreConstraint::new(),)
}

struct JsspScoreConstraint {
    constraint_ref: ConstraintRef,
}

impl JsspScoreConstraint {
    fn new() -> Self {
        Self {
            constraint_ref: ConstraintRef::new("", "jsspSchedule"),
        }
    }

    fn score(solution: &JsspPlan) -> HardSoftScore {
        let evaluation = solution.evaluate_schedule();
        HardSoftScore::of(
            -(evaluation.hard_penalty as i64),
            -(evaluation.makespan as i64),
        )
    }

    fn match_count(solution: &JsspPlan) -> usize {
        let evaluation = solution.evaluate_schedule();
        evaluation.hard_penalty + usize::from(evaluation.makespan > 0)
    }
}

impl ConstraintSet<JsspPlan, HardSoftScore> for JsspScoreConstraint {
    fn evaluate_all(&self, solution: &JsspPlan) -> HardSoftScore {
        Self::score(solution)
    }

    fn constraint_count(&self) -> usize {
        1
    }

    fn constraint_metadata_entries(&self) -> Vec<ConstraintMetadata<'_>> {
        vec![ConstraintMetadata::new(&self.constraint_ref, true)]
    }

    fn evaluate_each<'a>(
        &'a self,
        solution: &JsspPlan,
    ) -> Vec<ConstraintResult<'a, HardSoftScore>> {
        vec![ConstraintResult {
            name: &self.constraint_ref.name,
            score: Self::score(solution),
            match_count: Self::match_count(solution),
            is_hard: true,
        }]
    }

    fn evaluate_detailed<'a>(
        &'a self,
        solution: &JsspPlan,
    ) -> Vec<ConstraintAnalysis<'a, HardSoftScore>> {
        vec![ConstraintAnalysis::new(
            &self.constraint_ref,
            HardSoftScore::ZERO,
            Self::score(solution),
            Vec::new(),
            true,
        )]
    }

    fn initialize_all(&mut self, solution: &JsspPlan) -> HardSoftScore {
        Self::score(solution)
    }

    fn on_insert_all(
        &mut self,
        solution: &JsspPlan,
        _entity_index: usize,
        _descriptor_index: usize,
    ) -> HardSoftScore {
        Self::score(solution)
    }

    fn on_retract_all(
        &mut self,
        solution: &JsspPlan,
        _entity_index: usize,
        _descriptor_index: usize,
    ) -> HardSoftScore {
        HardSoftScore::ZERO - Self::score(solution)
    }

    fn reset_all(&mut self) {}
}
