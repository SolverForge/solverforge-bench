package com.solverforgebench.deliveries;

import ai.timefold.solver.core.api.score.HardSoftScore;
import ai.timefold.solver.core.api.score.stream.Constraint;
import ai.timefold.solver.core.api.score.stream.ConstraintFactory;
import ai.timefold.solver.core.api.score.stream.ConstraintProvider;

import com.solverforgebench.deliveries.domain.Delivery;
import com.solverforgebench.deliveries.domain.Vehicle;

/**
 * The solverforge-deliveries ruleset. Weights mirror the SolverForge model and
 * the benchmark validator; scripts/verify_model_parity.py pins them.
 */
public class DeliveryConstraintProvider implements ConstraintProvider {

    static final long UNASSIGNED_DELIVERY_HARD = 1_000_000L;

    @Override
    public Constraint[] defineConstraints(ConstraintFactory factory) {
        return new Constraint[]{
                allDeliveriesAssigned(factory),
                vehicleCapacity(factory),
                deliveryTimeWindows(factory),
                totalTravelTime(factory),
        };
    }

    Constraint allDeliveriesAssigned(ConstraintFactory factory) {
        return factory.forEachIncludingUnassigned(Delivery.class)
                .filter(delivery -> delivery.getVehicle() == null)
                .penalize(HardSoftScore.ofHard(UNASSIGNED_DELIVERY_HARD))
                .asConstraint("all_deliveries_assigned");
    }

    Constraint vehicleCapacity(ConstraintFactory factory) {
        return factory.forEach(Vehicle.class)
                .filter(vehicle -> vehicle.capacityOverage() > 0)
                .penalize(HardSoftScore.ONE_HARD, Vehicle::capacityOverage)
                .asConstraint("vehicle_capacity");
    }

    Constraint deliveryTimeWindows(ConstraintFactory factory) {
        return factory.forEach(Vehicle.class)
                .filter(vehicle -> vehicle.timeWindowViolationSeconds() > 0)
                .penalize(HardSoftScore.ONE_HARD, Vehicle::timeWindowViolationSeconds)
                .asConstraint("delivery_time_windows");
    }

    Constraint totalTravelTime(ConstraintFactory factory) {
        return factory.forEach(Vehicle.class)
                .filter(vehicle -> vehicle.travelSeconds() > 0)
                .penalize(HardSoftScore.ONE_SOFT, Vehicle::travelSeconds)
                .asConstraint("total_travel_time");
    }
}
