package com.cvrpbenchmark;

import ai.timefold.solver.core.api.score.HardSoftScore;
import ai.timefold.solver.core.api.score.stream.Constraint;
import ai.timefold.solver.core.api.score.stream.ConstraintCollectors;
import ai.timefold.solver.core.api.score.stream.ConstraintFactory;
import ai.timefold.solver.core.api.score.stream.ConstraintProvider;

import com.cvrpbenchmark.domain.DistanceMatrix;
import com.cvrpbenchmark.domain.Vehicle;
import com.cvrpbenchmark.domain.Visit;

public class CvrpConstraintProvider implements ConstraintProvider {

    @Override
    public Constraint[] defineConstraints(ConstraintFactory factory) {
        return new Constraint[]{
                vehicleCapacity(factory),
                depotToFirstVisit(factory),
                visitToVisit(factory),
                lastVisitToDepot(factory),
        };
    }

    // Hard constraint: total demand on each vehicle must not exceed its capacity
    Constraint vehicleCapacity(ConstraintFactory factory) {
        return factory.forEach(Vehicle.class)
                .filter(vehicle -> vehicle.getTotalDemand() > vehicle.getCapacity())
                .penalize(HardSoftScore.ONE_HARD,
                        vehicle -> vehicle.getTotalDemand() - vehicle.getCapacity())
                .asConstraint("vehicleCapacity");
    }

    // Soft constraint: distance from depot to first visit on each route
    Constraint depotToFirstVisit(ConstraintFactory factory) {
        return factory.forEach(Visit.class)
                .filter(visit -> visit.getVehicle() != null && visit.getPreviousVisit() == null)
                .join(DistanceMatrix.class)
                .penalize(HardSoftScore.ONE_SOFT,
                        (visit, dm) -> dm.getDistance(
                                visit.getVehicle().getHomeLocation(),
                                visit.getLocation()))
                .asConstraint("depotToFirstVisit");
    }

    // Soft constraint: distance between consecutive visits on a route
    Constraint visitToVisit(ConstraintFactory factory) {
        return factory.forEach(Visit.class)
                .filter(visit -> visit.getPreviousVisit() != null)
                .join(DistanceMatrix.class)
                .penalize(HardSoftScore.ONE_SOFT,
                        (visit, dm) -> dm.getDistance(
                                visit.getPreviousVisit().getLocation(),
                                visit.getLocation()))
                .asConstraint("visitToVisit");
    }

    // Soft constraint: distance from last visit back to depot
    Constraint lastVisitToDepot(ConstraintFactory factory) {
        return factory.forEach(Visit.class)
                .filter(visit -> visit.getVehicle() != null && visit.getNextVisit() == null)
                .join(DistanceMatrix.class)
                .penalize(HardSoftScore.ONE_SOFT,
                        (visit, dm) -> dm.getDistance(
                                visit.getLocation(),
                                visit.getVehicle().getHomeLocation()))
                .asConstraint("lastVisitToDepot");
    }
}
