use solverforge::prelude::*;
use solverforge::stream::joiner::equal_bi;

use crate::domain::{CvrpPlan, CvrpPlanConstraintStreams, Route};

pub fn define_constraints() -> impl ConstraintSet<CvrpPlan, HardSoftScore> {
    let all_customers_assigned = ConstraintFactory::<CvrpPlan, HardSoftScore>::new()
        .customers()
        .if_not_exists((
            ConstraintFactory::<CvrpPlan, HardSoftScore>::new()
                .routes()
                .flattened(|route: &Route| &route.visits),
            equal_bi(
                |customer: &crate::domain::Customer| customer.id,
                |assigned: &usize| *assigned,
            ),
        ))
        .penalize_hard()
        .named("all_customers_assigned");

    let capacity = ConstraintFactory::<CvrpPlan, HardSoftScore>::new()
        .routes()
        .filter(|route: &Route| !route.is_empty())
        .penalize_hard_with(|route: &Route| HardSoftScore::of(route.overload(), 0))
        .named("vehicle_capacity");

    let total_distance = ConstraintFactory::<CvrpPlan, HardSoftScore>::new()
        .routes()
        .filter(|route: &Route| !route.is_empty())
        .penalize_with(|route: &Route| HardSoftScore::of(0, route.total_distance()))
        .named("total_distance");

    (all_customers_assigned, capacity, total_distance)
}
