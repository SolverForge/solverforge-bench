package com.solverforgebench.jssp.domain;

import ai.timefold.solver.core.api.domain.common.PlanningId;
import ai.timefold.solver.core.api.domain.entity.PlanningEntity;
import ai.timefold.solver.core.api.domain.valuerange.ValueRangeProvider;
import ai.timefold.solver.core.api.domain.variable.PlanningListVariable;

import java.util.ArrayList;
import java.util.List;

@PlanningEntity
public class MachineSequence {

    @PlanningId
    private int id;

    private List<OperationAssignment> eligibleOperations = new ArrayList<>();

    @PlanningListVariable(valueRangeProviderRefs = "machineOperationRange")
    private List<OperationAssignment> operations = new ArrayList<>();

    public MachineSequence() {
    }

    public MachineSequence(int id, List<OperationAssignment> eligibleOperations) {
        this.id = id;
        this.eligibleOperations = eligibleOperations;
    }

    public int getId() {
        return id;
    }

    public List<OperationAssignment> getOperations() {
        return operations;
    }

    public void setOperations(List<OperationAssignment> operations) {
        this.operations = operations;
    }

    @ValueRangeProvider(id = "machineOperationRange")
    public List<OperationAssignment> getEligibleOperations() {
        return eligibleOperations;
    }

    public void setEligibleOperations(List<OperationAssignment> eligibleOperations) {
        this.eligibleOperations = eligibleOperations;
    }
}
