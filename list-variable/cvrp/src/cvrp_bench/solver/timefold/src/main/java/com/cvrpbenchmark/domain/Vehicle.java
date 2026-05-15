package com.cvrpbenchmark.domain;

import ai.timefold.solver.core.api.domain.entity.PlanningEntity;
import ai.timefold.solver.core.api.domain.variable.PlanningListVariable;

import java.util.ArrayList;
import java.util.List;

@PlanningEntity
public class Vehicle {

    private String id;
    private int capacity;
    private int homeLocation;

    @PlanningListVariable
    private List<Visit> visits;

    // Required by Timefold
    public Vehicle() {}

    public Vehicle(String id, int capacity, int homeLocation) {
        this.id = id;
        this.capacity = capacity;
        this.homeLocation = homeLocation;
        this.visits = new ArrayList<>();
    }

    public String getId() { return id; }

    public int getCapacity() { return capacity; }

    public int getHomeLocation() { return homeLocation; }

    public List<Visit> getVisits() { return visits; }

    public void setVisits(List<Visit> visits) { this.visits = visits; }

    public int getTotalDemand() {
        return visits.stream().mapToInt(Visit::getDemand).sum();
    }
}
