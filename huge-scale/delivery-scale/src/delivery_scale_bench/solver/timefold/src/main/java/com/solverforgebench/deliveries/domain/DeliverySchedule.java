package com.solverforgebench.deliveries.domain;

import ai.timefold.solver.core.api.domain.solution.PlanningEntityCollectionProperty;
import ai.timefold.solver.core.api.domain.solution.PlanningScore;
import ai.timefold.solver.core.api.domain.solution.PlanningSolution;
import ai.timefold.solver.core.api.domain.valuerange.ValueRangeProvider;
import ai.timefold.solver.core.api.score.HardSoftScore;

import java.util.List;

@PlanningSolution
public class DeliverySchedule {

    @PlanningEntityCollectionProperty
    @ValueRangeProvider
    private List<Delivery> deliveries;

    @PlanningEntityCollectionProperty
    private List<Vehicle> vehicles;

    @PlanningScore
    private HardSoftScore score;

    public DeliverySchedule() {
    }

    public DeliverySchedule(List<Delivery> deliveries, List<Vehicle> vehicles) {
        this.deliveries = deliveries;
        this.vehicles = vehicles;
    }

    public List<Delivery> getDeliveries() {
        return deliveries;
    }

    public List<Vehicle> getVehicles() {
        return vehicles;
    }

    public HardSoftScore getScore() {
        return score;
    }

    public void setScore(HardSoftScore score) {
        this.score = score;
    }
}
