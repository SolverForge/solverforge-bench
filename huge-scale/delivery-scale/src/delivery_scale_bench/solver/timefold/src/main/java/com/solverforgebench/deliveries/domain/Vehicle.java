package com.solverforgebench.deliveries.domain;

import ai.timefold.solver.core.api.domain.common.PlanningId;
import ai.timefold.solver.core.api.domain.entity.PlanningEntity;
import ai.timefold.solver.core.api.domain.variable.PlanningListVariable;

import java.util.ArrayList;
import java.util.List;

/** A vehicle owning one route; the route is the list planning variable. */
@PlanningEntity
public class Vehicle {

    @PlanningId
    private int index;
    private Depot depot;

    @PlanningListVariable
    private List<Delivery> deliveries = new ArrayList<>();

    public Vehicle() {
    }

    public Vehicle(int index, Depot depot) {
        this.index = index;
        this.depot = depot;
    }

    public int getIndex() {
        return index;
    }

    public List<Delivery> getDeliveries() {
        return deliveries;
    }

    public void setDeliveries(List<Delivery> deliveries) {
        this.deliveries = deliveries;
    }

    public long capacityOverage() {
        long load = 0;
        for (Delivery delivery : deliveries) {
            load += delivery.getDemand();
        }
        return Math.max(0L, load - depot.capacity());
    }

    /** Depot to every stop and back, under the shared integer travel rule. */
    public long travelSeconds() {
        if (deliveries.isEmpty()) {
            return 0L;
        }
        long travel = 0;
        long x = depot.x();
        long y = depot.y();
        for (Delivery delivery : deliveries) {
            travel += Depot.travelSeconds(x, y, delivery.getX(), delivery.getY());
            x = delivery.getX();
            y = delivery.getY();
        }
        return travel + Depot.travelSeconds(x, y, depot.x(), depot.y());
    }

    /** Seconds by which services end after their window, waiting before minStart. */
    public long timeWindowViolationSeconds() {
        long clock = depot.departureTime();
        long lateness = 0;
        long x = depot.x();
        long y = depot.y();
        for (Delivery delivery : deliveries) {
            clock += Depot.travelSeconds(x, y, delivery.getX(), delivery.getY());
            clock = Math.max(clock, delivery.getMinStart()) + delivery.getService();
            lateness += Math.max(0L, clock - delivery.getMaxEnd());
            x = delivery.getX();
            y = delivery.getY();
        }
        return lateness;
    }

    @Override
    public String toString() {
        return "Vehicle-" + index;
    }
}
