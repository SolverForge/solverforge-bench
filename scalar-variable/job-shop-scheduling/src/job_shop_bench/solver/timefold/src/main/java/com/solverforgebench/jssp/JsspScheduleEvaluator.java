package com.solverforgebench.jssp;

import ai.timefold.solver.core.api.score.HardSoftScore;

import com.solverforgebench.jssp.domain.JsspSchedule;
import com.solverforgebench.jssp.domain.MachineSequence;
import com.solverforgebench.jssp.domain.OperationAssignment;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class JsspScheduleEvaluator {

    private JsspScheduleEvaluator() {
    }

    public record Evaluation(int[] starts, boolean[] startKnown, int makespan, int hardPenalty) {

        public HardSoftScore score() {
            return HardSoftScore.of(-hardPenalty, -makespan);
        }

        public int startFor(OperationAssignment operation) {
            int operationId = operation.getId();
            if (operationId < 0 || operationId >= starts.length || !startKnown[operationId]) {
                return 0;
            }
            return starts[operationId];
        }
    }

    public static Evaluation evaluate(JsspSchedule schedule) {
        List<OperationAssignment> operations = schedule.getOperations();
        int operationCount = operations == null ? 0 : operations.size();
        int hardPenalty = 0;

        OperationAssignment[] byId = new OperationAssignment[operationCount];
        for (OperationAssignment operation : operations) {
            int operationId = operation.getId();
            if (operationId >= 0 && operationId < operationCount) {
                byId[operationId] = operation;
            } else {
                hardPenalty++;
            }
        }

        List<List<Integer>> edges = new ArrayList<>(operationCount);
        for (int i = 0; i < operationCount; i++) {
            edges.add(new ArrayList<>());
        }
        int[] indegree = new int[operationCount];
        int jobCount = Math.max(schedule.getNumJobs(), operations.stream()
                .mapToInt(operation -> operation.getJobId() + 1)
                .max()
                .orElse(0));
        List<List<OperationAssignment>> operationsByJob = new ArrayList<>(jobCount);
        for (int i = 0; i < jobCount; i++) {
            operationsByJob.add(new ArrayList<>());
        }
        for (OperationAssignment operation : operations) {
            if (operation.getJobId() >= 0 && operation.getJobId() < operationsByJob.size()) {
                operationsByJob.get(operation.getJobId()).add(operation);
            }
        }
        for (List<OperationAssignment> jobOperations : operationsByJob) {
            jobOperations.sort(Comparator.comparingInt(OperationAssignment::getOpIndex));
            for (int i = 0; i + 1 < jobOperations.size(); i++) {
                addEdge(jobOperations.get(i).getId(), jobOperations.get(i + 1).getId(), edges, indegree);
            }
        }

        int[] assignedCounts = new int[operationCount];
        List<MachineSequence> machineSequences = schedule.getMachineSequences();
        if (machineSequences != null) {
            for (MachineSequence machine : machineSequences) {
                List<OperationAssignment> machineOperations = machine.getOperations();
                if (machine.getId() >= schedule.getNumMachines()) {
                    hardPenalty += machineOperations.size();
                }
                for (OperationAssignment operation : machineOperations) {
                    int operationId = operation.getId();
                    if (operationId < 0 || operationId >= operationCount || byId[operationId] == null) {
                        hardPenalty++;
                        continue;
                    }
                    assignedCounts[operationId]++;
                    if (operation.getMachineId() != machine.getId()) {
                        hardPenalty++;
                    }
                }
                for (int i = 0; i + 1 < machineOperations.size(); i++) {
                    addEdge(machineOperations.get(i).getId(), machineOperations.get(i + 1).getId(), edges, indegree);
                }
            }
        }

        for (int count : assignedCounts) {
            if (count == 0) {
                hardPenalty++;
            } else if (count > 1) {
                hardPenalty += count - 1;
            }
        }

        int[] starts = new int[operationCount];
        boolean[] startKnown = new boolean[operationCount];
        int[] earliest = new int[operationCount];
        ArrayDeque<Integer> ready = new ArrayDeque<>();
        for (int i = 0; i < operationCount; i++) {
            if (indegree[i] == 0) {
                ready.add(i);
            }
        }

        int processed = 0;
        while (!ready.isEmpty()) {
            int operationId = ready.removeFirst();
            OperationAssignment operation = byId[operationId];
            if (operation == null) {
                continue;
            }
            processed++;
            starts[operationId] = earliest[operationId];
            startKnown[operationId] = true;
            int finish = earliest[operationId] + operation.getDuration();
            for (int nextId : edges.get(operationId)) {
                earliest[nextId] = Math.max(earliest[nextId], finish);
                indegree[nextId]--;
                if (indegree[nextId] == 0) {
                    ready.add(nextId);
                }
            }
        }

        if (processed < operationCount) {
            hardPenalty += operationCount - processed;
        }

        int makespan = 0;
        for (OperationAssignment operation : operations) {
            int operationId = operation.getId();
            if (operationId >= 0 && operationId < operationCount && startKnown[operationId]) {
                makespan = Math.max(makespan, starts[operationId] + operation.getDuration());
            }
        }

        return new Evaluation(starts, startKnown, makespan, hardPenalty);
    }

    private static void addEdge(int from, int to, List<List<Integer>> edges, int[] indegree) {
        if (from < 0 || to < 0 || from >= edges.size() || to >= edges.size()) {
            return;
        }
        edges.get(from).add(to);
        indegree[to]++;
    }
}
