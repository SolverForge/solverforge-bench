package com.cvrpbenchmark.domain;

import ai.timefold.solver.core.api.domain.entity.PlanningEntity;
import ai.timefold.solver.core.api.domain.variable.InverseRelationShadowVariable;
import ai.timefold.solver.core.api.domain.variable.NextElementShadowVariable;
import ai.timefold.solver.core.api.domain.variable.PreviousElementShadowVariable;

@PlanningEntity
public class Visit {

    private int id;
    private int location;
    private int demand;

    @InverseRelationShadowVariable(sourceVariableName = "visits")
    private Vehicle vehicle;

    @PreviousElementShadowVariable(sourceVariableName = "visits")
    private Visit previousVisit;

    @NextElementShadowVariable(sourceVariableName = "visits")
    private Visit nextVisit;

    // Required by Timefold
    public Visit() {}

    public Visit(int id, int location, int demand) {
        this.id = id;
        this.location = location;
        this.demand = demand;
    }

    public int getId() { return id; }

    public int getLocation() { return location; }

    public int getDemand() { return demand; }

    public Vehicle getVehicle() { return vehicle; }

    public void setVehicle(Vehicle vehicle) { this.vehicle = vehicle; }

    public Visit getPreviousVisit() { return previousVisit; }

    public void setPreviousVisit(Visit previousVisit) { this.previousVisit = previousVisit; }

    public Visit getNextVisit() { return nextVisit; }

    public void setNextVisit(Visit nextVisit) { this.nextVisit = nextVisit; }
}
