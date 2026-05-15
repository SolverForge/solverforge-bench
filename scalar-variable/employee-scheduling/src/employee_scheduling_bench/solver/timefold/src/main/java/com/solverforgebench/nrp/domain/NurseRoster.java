package com.solverforgebench.nrp.domain;

import ai.timefold.solver.core.api.domain.solution.PlanningEntityCollectionProperty;
import ai.timefold.solver.core.api.domain.solution.PlanningScore;
import ai.timefold.solver.core.api.domain.solution.PlanningSolution;
import ai.timefold.solver.core.api.domain.solution.ProblemFactCollectionProperty;
import ai.timefold.solver.core.api.score.HardSoftScore;

import java.util.List;

@PlanningSolution
public class NurseRoster {

    @ProblemFactCollectionProperty
    private List<NurseFact> nurses;

    @PlanningEntityCollectionProperty
    private List<ShiftAssignment> assignments;

    @PlanningScore
    private HardSoftScore score;

    public NurseRoster() {
    }

    public NurseRoster(List<NurseFact> nurses, List<ShiftAssignment> assignments) {
        this.nurses = nurses;
        this.assignments = assignments;
    }

    public List<NurseFact> getNurses() {
        return nurses;
    }

    public List<ShiftAssignment> getAssignments() {
        return assignments;
    }

    public HardSoftScore getScore() {
        return score;
    }

    public void setScore(HardSoftScore score) {
        this.score = score;
    }
}
