//! The solverforge-deliveries ruleset. Weights are mirrored by the Timefold
//! model and the validator; `scripts/verify_model_parity.py` pins them.

use solverforge::prelude::*;
use solverforge::stream::joiner::equal_bi;

use crate::domain::{Delivery, DeliveryPlan, Vehicle};

const UNASSIGNED_DELIVERY_HARD: i64 = 1_000_000;

#[solverforge_constraints]
pub fn define_constraints() -> impl ConstraintSet<DeliveryPlan, HardSoftScore> {
    let all_deliveries_assigned = ConstraintFactory::<DeliveryPlan, HardSoftScore>::new()
        .for_each(DeliveryPlan::deliveries())
        .if_not_exists((
            ConstraintFactory::<DeliveryPlan, HardSoftScore>::new()
                .for_each(DeliveryPlan::vehicles())
                .flattened(|vehicle: &Vehicle| &vehicle.delivery_order),
            equal_bi(
                |delivery: &Delivery| delivery.id,
                |assigned: &usize| *assigned,
            ),
        ))
        .penalize(HardSoftScore::of_hard(UNASSIGNED_DELIVERY_HARD))
        .named("all_deliveries_assigned");

    let vehicle_capacity = ConstraintFactory::<DeliveryPlan, HardSoftScore>::new()
        .for_each(DeliveryPlan::vehicles())
        .filter(|vehicle: &Vehicle| vehicle.route_capacity_overage > 0)
        .penalize(hard_weight(|vehicle: &Vehicle| {
            HardSoftScore::of_hard(vehicle.route_capacity_overage)
        }))
        .named("vehicle_capacity");

    let delivery_time_windows = ConstraintFactory::<DeliveryPlan, HardSoftScore>::new()
        .for_each(DeliveryPlan::vehicles())
        .filter(|vehicle: &Vehicle| vehicle.route_time_window_violation_seconds > 0)
        .penalize(hard_weight(|vehicle: &Vehicle| {
            HardSoftScore::of_hard(vehicle.route_time_window_violation_seconds)
        }))
        .named("delivery_time_windows");

    let total_travel_time = ConstraintFactory::<DeliveryPlan, HardSoftScore>::new()
        .for_each(DeliveryPlan::vehicles())
        .filter(|vehicle: &Vehicle| vehicle.route_travel_seconds > 0)
        .penalize(|vehicle: &Vehicle| HardSoftScore::of_soft(vehicle.route_travel_seconds))
        .named("total_travel_time");

    (
        all_deliveries_assigned,
        vehicle_capacity,
        delivery_time_windows,
        total_travel_time,
    )
}
