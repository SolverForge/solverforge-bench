package com.solverforgebench.jssp.domain;

import ai.timefold.solver.core.api.domain.common.PlanningId;
import ai.timefold.solver.core.api.domain.entity.PlanningEntity;
import ai.timefold.solver.core.api.domain.variable.InverseRelationShadowVariable;
import ai.timefold.solver.core.api.domain.variable.NextElementShadowVariable;
import ai.timefold.solver.core.api.domain.variable.PreviousElementShadowVariable;

@PlanningEntity
public class OperationAssignment {

    @PlanningId
    private int id;
    private int jobId;
    private int opIndex;
    private int machineId;
    private int duration;

    @InverseRelationShadowVariable(sourceVariableName = "operations")
    private MachineSequence machineSequence;

    @PreviousElementShadowVariable(sourceVariableName = "operations")
    private OperationAssignment previousOnMachine;

    @NextElementShadowVariable(sourceVariableName = "operations")
    private OperationAssignment nextOnMachine;

    private Integer start;

    public OperationAssignment() {
    }

    public OperationAssignment(int id, int jobId, int opIndex, int machineId, int duration) {
        this.id = id;
        this.jobId = jobId;
        this.opIndex = opIndex;
        this.machineId = machineId;
        this.duration = duration;
    }

    public int getId() {
        return id;
    }

    public int getJobId() {
        return jobId;
    }

    public int getOpIndex() {
        return opIndex;
    }

    public int getMachineId() {
        return machineId;
    }

    public int getDuration() {
        return duration;
    }

    public Integer getStart() {
        return start;
    }

    public void setStart(Integer start) {
        this.start = start;
    }

    public boolean isAssigned() {
        return machineSequence != null;
    }

    public int getEnd() {
        return start == null ? 0 : start + duration;
    }

    public MachineSequence getMachineSequence() {
        return machineSequence;
    }

    public void setMachineSequence(MachineSequence machineSequence) {
        this.machineSequence = machineSequence;
    }

    public OperationAssignment getPreviousOnMachine() {
        return previousOnMachine;
    }

    public void setPreviousOnMachine(OperationAssignment previousOnMachine) {
        this.previousOnMachine = previousOnMachine;
    }

    public OperationAssignment getNextOnMachine() {
        return nextOnMachine;
    }

    public void setNextOnMachine(OperationAssignment nextOnMachine) {
        this.nextOnMachine = nextOnMachine;
    }
}
