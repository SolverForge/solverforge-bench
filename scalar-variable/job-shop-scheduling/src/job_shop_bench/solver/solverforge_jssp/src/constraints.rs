use std::collections::BTreeMap;

use solverforge::prelude::*;
use solverforge::stream::collector::{Accumulator, Collector};

use crate::domain::{JsspOperation, JsspPlan};

pub fn define_constraints() -> impl ConstraintSet<JsspPlan, HardSoftScore> {
    let assigned_start = ConstraintFactory::<JsspPlan, HardSoftScore>::new()
        .for_each(JsspPlan::operations())
        .unassigned()
        .penalize(HardSoftScore::ONE_HARD)
        .named("assignedStart");

    let job_precedence = ConstraintFactory::<JsspPlan, HardSoftScore>::new()
        .for_each(JsspPlan::operations())
        .join((
            ConstraintFactory::<JsspPlan, HardSoftScore>::new().for_each(JsspPlan::operations()),
            |left: &JsspOperation, right: &JsspOperation| {
                left.job_id == right.job_id
                    && left.op_index + 1 == right.op_index
                    && left.start.is_some()
                    && right.start.is_some()
            },
        ))
        .penalize(precedence_penalty as fn(&JsspOperation, &JsspOperation) -> HardSoftScore)
        .named("jobPrecedence");

    let machine_no_overlap = ConstraintFactory::<JsspPlan, HardSoftScore>::new()
        .for_each(JsspPlan::operations())
        .join((
            ConstraintFactory::<JsspPlan, HardSoftScore>::new().for_each(JsspPlan::operations()),
            |left: &JsspOperation, right: &JsspOperation| {
                left.id < right.id
                    && left.machine_id == right.machine_id
                    && left.start.is_some()
                    && right.start.is_some()
                    && overlaps(left, right)
            },
        ))
        .penalize(overlap_penalty as fn(&JsspOperation, &JsspOperation) -> HardSoftScore)
        .named("machineNoOverlap");

    let makespan = ConstraintFactory::<JsspPlan, HardSoftScore>::new()
        .for_each(JsspPlan::operations())
        .filter(|operation: &JsspOperation| operation.start.is_some())
        .group_by(|_operation: &JsspOperation| 0usize, MaxEndCollector)
        .penalize(|_group: &usize, makespan: &usize| HardSoftScore::of_soft(*makespan as i64))
        .named("makespan");

    (assigned_start, job_precedence, machine_no_overlap, makespan)
}

fn precedence_penalty(previous: &JsspOperation, next: &JsspOperation) -> HardSoftScore {
    let violation = previous
        .end()
        .zip(next.start)
        .map(|(previous_end, next_start)| previous_end.saturating_sub(next_start))
        .unwrap_or(1);
    HardSoftScore::of_hard(violation as i64)
}

fn overlaps(left: &JsspOperation, right: &JsspOperation) -> bool {
    let (Some(left_start), Some(left_end), Some(right_start), Some(right_end)) =
        (left.start, left.end(), right.start, right.end())
    else {
        return false;
    };
    left_start < right_end && right_start < left_end
}

fn overlap_penalty(left: &JsspOperation, right: &JsspOperation) -> HardSoftScore {
    let (Some(left_start), Some(left_end), Some(right_start), Some(right_end)) =
        (left.start, left.end(), right.start, right.end())
    else {
        return HardSoftScore::of_hard(1);
    };
    let overlap = left_end
        .min(right_end)
        .saturating_sub(left_start.max(right_start));
    HardSoftScore::of_hard(overlap as i64)
}

struct MaxEndCollector;

impl Collector<&JsspOperation> for MaxEndCollector {
    type Value = usize;
    type Result = usize;
    type Accumulator = MaxEndAccumulator;

    fn extract(&self, operation: &JsspOperation) -> Self::Value {
        operation.end().unwrap_or(0)
    }

    fn create_accumulator(&self) -> Self::Accumulator {
        MaxEndAccumulator {
            counts_by_end: BTreeMap::new(),
            max_end: 0,
        }
    }
}

struct MaxEndAccumulator {
    counts_by_end: BTreeMap<usize, usize>,
    max_end: usize,
}

impl Accumulator<usize, usize> for MaxEndAccumulator {
    type Retraction = usize;

    fn accumulate(&mut self, end: usize) -> Self::Retraction {
        *self.counts_by_end.entry(end).or_insert(0) += 1;
        self.max_end = self.max_end.max(end);
        end
    }

    fn retract(&mut self, end: Self::Retraction) {
        if let Some(count) = self.counts_by_end.get_mut(&end) {
            *count -= 1;
            if *count == 0 {
                self.counts_by_end.remove(&end);
            }
        }
        if end == self.max_end {
            self.max_end = self
                .counts_by_end
                .last_key_value()
                .map_or(0, |(end, _)| *end);
        }
    }

    fn with_result<T>(&self, f: impl FnOnce(&usize) -> T) -> T {
        f(&self.max_end)
    }

    fn reset(&mut self) {
        self.counts_by_end.clear();
        self.max_end = 0;
    }
}
