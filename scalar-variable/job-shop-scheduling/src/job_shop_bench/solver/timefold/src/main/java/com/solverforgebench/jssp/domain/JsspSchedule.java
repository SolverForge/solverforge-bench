package com.solverforgebench.jssp.domain;

import ai.timefold.solver.core.api.domain.solution.PlanningEntityCollectionProperty;
import ai.timefold.solver.core.api.domain.solution.PlanningScore;
import ai.timefold.solver.core.api.domain.solution.PlanningSolution;
import ai.timefold.solver.core.api.domain.solution.ProblemFactCollectionProperty;
import ai.timefold.solver.core.api.domain.valuerange.ValueRangeProvider;
import ai.timefold.solver.core.api.score.HardSoftScore;

import java.util.List;

@PlanningSolution
public class JsspSchedule {

    @ProblemFactCollectionProperty
    @ValueRangeProvider(id = "startRange")
    private List<Integer> startRange;

    @PlanningEntityCollectionProperty
    private List<OperationAssignment> operations;

    @PlanningScore
    private HardSoftScore score;

    public JsspSchedule() {
    }

    public JsspSchedule(List<Integer> startRange, List<OperationAssignment> operations) {
        this.startRange = startRange;
        this.operations = operations;
    }

    public List<Integer> getStartRange() {
        return startRange;
    }

    public List<OperationAssignment> getOperations() {
        return operations;
    }

    public HardSoftScore getScore() {
        return score;
    }

    public void setScore(HardSoftScore score) {
        this.score = score;
    }
}
