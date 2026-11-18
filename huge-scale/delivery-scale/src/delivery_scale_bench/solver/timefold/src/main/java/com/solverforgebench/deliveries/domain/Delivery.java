package com.solverforgebench.deliveries.domain;

import ai.timefold.solver.core.api.domain.common.PlanningId;
import ai.timefold.solver.core.api.domain.entity.PlanningEntity;
import ai.timefold.solver.core.api.domain.variable.InverseRelationShadowVariable;

/** A delivery stop; the inverse shadow names the vehicle that serves it. */
@PlanningEntity
public class Delivery {

    @PlanningId
    private int index;
    private long x;
    private long y;
    private long demand;
    private long minStart;
    private long maxEnd;
    private long service;

    @InverseRelationShadowVariable(sourceVariableName = "deliveries")
    private Vehicle vehicle;

    public Delivery() {
    }

    public Delivery(int index, long x, long y, long demand, long minStart, long maxEnd, long service) {
        this.index = index;
        this.x = x;
        this.y = y;
        this.demand = demand;
        this.minStart = minStart;
        this.maxEnd = maxEnd;
        this.service = service;
    }

    public int getIndex() {
        return index;
    }

    public long getX() {
        return x;
    }

    public long getY() {
        return y;
    }

    public long getDemand() {
        return demand;
    }

    public long getMinStart() {
        return minStart;
    }

    public long getMaxEnd() {
        return maxEnd;
    }

    public long getService() {
        return service;
    }

    public Vehicle getVehicle() {
        return vehicle;
    }

    public void setVehicle(Vehicle vehicle) {
        this.vehicle = vehicle;
    }

    @Override
    public String toString() {
        return "Delivery-" + index;
    }
}
