package com.cvrpbenchmark.domain;

import ai.timefold.solver.core.api.domain.solution.PlanningEntityCollectionProperty;
import ai.timefold.solver.core.api.domain.solution.PlanningScore;
import ai.timefold.solver.core.api.domain.solution.PlanningSolution;
import ai.timefold.solver.core.api.domain.solution.ProblemFactProperty;
import ai.timefold.solver.core.api.domain.valuerange.ValueRangeProvider;
import ai.timefold.solver.core.api.score.buildin.hardsoft.HardSoftScore;

import java.util.List;

@PlanningSolution
public class VehicleRoutePlan {

    @PlanningEntityCollectionProperty
    private List<Vehicle> vehicles;

    @PlanningEntityCollectionProperty
    @ValueRangeProvider
    private List<Visit> visits;

    @ProblemFactProperty
    private DistanceMatrix distanceMatrix;

    @PlanningScore
    private HardSoftScore score;

    // Required by Timefold
    public VehicleRoutePlan() {}

    public VehicleRoutePlan(List<Vehicle> vehicles, List<Visit> visits, DistanceMatrix distanceMatrix) {
        this.vehicles = vehicles;
        this.visits = visits;
        this.distanceMatrix = distanceMatrix;
    }

    public List<Vehicle> getVehicles() { return vehicles; }

    public List<Visit> getVisits() { return visits; }

    public DistanceMatrix getDistanceMatrix() { return distanceMatrix; }

    public HardSoftScore getScore() { return score; }

    public void setScore(HardSoftScore score) { this.score = score; }
}
