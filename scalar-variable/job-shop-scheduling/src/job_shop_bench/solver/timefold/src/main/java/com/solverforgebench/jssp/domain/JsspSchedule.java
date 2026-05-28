package com.solverforgebench.jssp.domain;

import ai.timefold.solver.core.api.domain.solution.PlanningEntityCollectionProperty;
import ai.timefold.solver.core.api.domain.solution.PlanningScore;
import ai.timefold.solver.core.api.domain.solution.PlanningSolution;
import ai.timefold.solver.core.api.score.HardSoftScore;

import java.util.List;

@PlanningSolution
public class JsspSchedule {

    private int numJobs;
    private int numMachines;

    @PlanningEntityCollectionProperty
    private List<MachineSequence> machineSequences;

    @PlanningEntityCollectionProperty
    private List<OperationAssignment> operations;

    @PlanningScore
    private HardSoftScore score;

    public JsspSchedule() {
    }

    public JsspSchedule(
            int numJobs,
            int numMachines,
            List<MachineSequence> machineSequences,
            List<OperationAssignment> operations) {
        this.numJobs = numJobs;
        this.numMachines = numMachines;
        this.machineSequences = machineSequences;
        this.operations = operations;
    }

    public int getNumJobs() {
        return numJobs;
    }

    public int getNumMachines() {
        return numMachines;
    }

    public List<MachineSequence> getMachineSequences() {
        return machineSequences;
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
