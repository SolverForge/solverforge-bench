package com.solverforgebench.jssp.domain;

import ai.timefold.solver.core.api.domain.common.PlanningId;
import ai.timefold.solver.core.api.domain.entity.PlanningEntity;
import ai.timefold.solver.core.api.domain.variable.PlanningVariable;

@PlanningEntity
public class OperationAssignment {

    @PlanningId
    private int id;
    private int jobId;
    private int opIndex;
    private int machineId;
    private int duration;

    @PlanningVariable(valueRangeProviderRefs = "startRange")
    private Integer start;

    public OperationAssignment() {
    }

    public OperationAssignment(int id, int jobId, int opIndex, int machineId, int duration, Integer start) {
        this.id = id;
        this.jobId = jobId;
        this.opIndex = opIndex;
        this.machineId = machineId;
        this.duration = duration;
        this.start = start;
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
        return start != null;
    }

    public int getEnd() {
        return start == null ? 0 : start + duration;
    }
}
