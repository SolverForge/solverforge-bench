package com.solverforgebench.nrp.domain;

import ai.timefold.solver.core.api.domain.entity.PlanningEntity;
import ai.timefold.solver.core.api.domain.lookup.PlanningId;
import ai.timefold.solver.core.api.domain.variable.PlanningVariable;

import java.util.List;

@PlanningEntity
public class ShiftAssignment {

    @PlanningId
    private int id;
    private int week;
    private int day;
    private int shiftTypeIdx;
    private int skillIdx;
    private boolean minimum;
    private List<Integer> forbiddenPredecessors;
    private List<Integer> shiftOffRequestNurses;

    @PlanningVariable(valueRangeProviderRefs = "nurseRange")
    private NurseFact nurse;

    public ShiftAssignment() {
    }

    public ShiftAssignment(
            int id,
            int week,
            int day,
            int shiftTypeIdx,
            int skillIdx,
            boolean minimum,
            List<Integer> forbiddenPredecessors,
            List<Integer> shiftOffRequestNurses) {
        this.id = id;
        this.week = week;
        this.day = day;
        this.shiftTypeIdx = shiftTypeIdx;
        this.skillIdx = skillIdx;
        this.minimum = minimum;
        this.forbiddenPredecessors = forbiddenPredecessors;
        this.shiftOffRequestNurses = shiftOffRequestNurses;
    }

    public int getId() {
        return id;
    }

    public int getWeek() {
        return week;
    }

    public int getDay() {
        return day;
    }

    public int getGlobalDay() {
        return week * 7 + day;
    }

    public int getShiftTypeIdx() {
        return shiftTypeIdx;
    }

    public int getSkillIdx() {
        return skillIdx;
    }

    public boolean isMinimum() {
        return minimum;
    }

    public List<Integer> getForbiddenPredecessors() {
        return forbiddenPredecessors;
    }

    public boolean hasForbiddenPredecessor(int shiftTypeIdx) {
        return forbiddenPredecessors != null && forbiddenPredecessors.contains(shiftTypeIdx);
    }

    public List<Integer> getShiftOffRequestNurses() {
        return shiftOffRequestNurses;
    }

    public NurseFact getNurse() {
        return nurse;
    }

    public void setNurse(NurseFact nurse) {
        this.nurse = nurse;
    }

    public boolean isAssigned() {
        return nurse != null && !nurse.isUnassigned();
    }

    public Integer getAssignedNurseIndex() {
        return isAssigned() ? nurse.getIndex() : null;
    }

    public int shiftOffRequestPenaltyForAssignedNurse() {
        if (!isAssigned() || shiftOffRequestNurses == null) {
            return 0;
        }
        int requestCount = 0;
        for (Integer requestNurse : shiftOffRequestNurses) {
            if (requestNurse == nurse.getIndex()) {
                requestCount++;
            }
        }
        return requestCount * 10;
    }
}
