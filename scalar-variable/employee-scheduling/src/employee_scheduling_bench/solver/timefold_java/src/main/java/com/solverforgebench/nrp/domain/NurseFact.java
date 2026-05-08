package com.solverforgebench.nrp.domain;

import ai.timefold.solver.core.api.domain.lookup.PlanningId;

import java.util.Set;

public class NurseFact {

    @PlanningId
    private String id;
    private int index;
    private Set<Integer> skills;
    private int minAssignments;
    private int maxAssignments;
    private int minConsecutiveWorking;
    private int maxConsecutiveWorking;
    private int minConsecutiveOff;
    private int maxConsecutiveOff;
    private int maxWorkingWeekends;
    private boolean completeWeekends;
    private int historyAssignments;
    private int historyWorkingWeekends;
    private Integer historyLastShiftTypeIdx;
    private int historyConsecutiveAssignments;
    private int historyConsecutiveWorking;
    private int historyConsecutiveOff;
    private int totalDays;
    private int[] shiftTypeMinConsecutive;
    private int[] shiftTypeMaxConsecutive;

    public NurseFact() {
    }

    public NurseFact(
            String id,
            int index,
            Set<Integer> skills,
            int minAssignments,
            int maxAssignments,
            int minConsecutiveWorking,
            int maxConsecutiveWorking,
            int minConsecutiveOff,
            int maxConsecutiveOff,
            int maxWorkingWeekends,
            boolean completeWeekends,
            int historyAssignments,
            int historyWorkingWeekends,
            Integer historyLastShiftTypeIdx,
            int historyConsecutiveAssignments,
            int historyConsecutiveWorking,
            int historyConsecutiveOff,
            int totalDays,
            int[] shiftTypeMinConsecutive,
            int[] shiftTypeMaxConsecutive) {
        this.id = id;
        this.index = index;
        this.skills = skills;
        this.minAssignments = minAssignments;
        this.maxAssignments = maxAssignments;
        this.minConsecutiveWorking = minConsecutiveWorking;
        this.maxConsecutiveWorking = maxConsecutiveWorking;
        this.minConsecutiveOff = minConsecutiveOff;
        this.maxConsecutiveOff = maxConsecutiveOff;
        this.maxWorkingWeekends = maxWorkingWeekends;
        this.completeWeekends = completeWeekends;
        this.historyAssignments = historyAssignments;
        this.historyWorkingWeekends = historyWorkingWeekends;
        this.historyLastShiftTypeIdx = historyLastShiftTypeIdx;
        this.historyConsecutiveAssignments = historyConsecutiveAssignments;
        this.historyConsecutiveWorking = historyConsecutiveWorking;
        this.historyConsecutiveOff = historyConsecutiveOff;
        this.totalDays = totalDays;
        this.shiftTypeMinConsecutive = shiftTypeMinConsecutive;
        this.shiftTypeMaxConsecutive = shiftTypeMaxConsecutive;
    }

    public String getId() {
        return id;
    }

    public int getIndex() {
        return index;
    }

    public Set<Integer> getSkills() {
        return skills;
    }

    public boolean isUnassigned() {
        return index < 0;
    }

    public boolean isRealNurse() {
        return index >= 0;
    }

    public int getMinAssignments() {
        return minAssignments;
    }

    public int getMaxAssignments() {
        return maxAssignments;
    }

    public int getMinConsecutiveWorking() {
        return minConsecutiveWorking;
    }

    public int getMaxConsecutiveWorking() {
        return maxConsecutiveWorking;
    }

    public int getMinConsecutiveOff() {
        return minConsecutiveOff;
    }

    public int getMaxConsecutiveOff() {
        return maxConsecutiveOff;
    }

    public int getMaxWorkingWeekends() {
        return maxWorkingWeekends;
    }

    public boolean isCompleteWeekends() {
        return completeWeekends;
    }

    public int getHistoryAssignments() {
        return historyAssignments;
    }

    public int getHistoryWorkingWeekends() {
        return historyWorkingWeekends;
    }

    public Integer getHistoryLastShiftTypeIdx() {
        return historyLastShiftTypeIdx;
    }

    public int getHistoryConsecutiveAssignments() {
        return historyConsecutiveAssignments;
    }

    public int getHistoryConsecutiveWorking() {
        return historyConsecutiveWorking;
    }

    public int getHistoryConsecutiveOff() {
        return historyConsecutiveOff;
    }

    public int getTotalDays() {
        return totalDays;
    }

    public int getShiftTypeCount() {
        return shiftTypeMinConsecutive == null ? 0 : shiftTypeMinConsecutive.length;
    }

    public int getShiftTypeMinConsecutive(int shiftTypeIdx) {
        return shiftTypeMinConsecutive[shiftTypeIdx];
    }

    public int getShiftTypeMaxConsecutive(int shiftTypeIdx) {
        return shiftTypeMaxConsecutive[shiftTypeIdx];
    }
}
