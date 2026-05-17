package com.solverforgebench.jssp;

import ai.timefold.solver.core.api.solver.Solver;
import ai.timefold.solver.core.api.solver.SolverFactory;
import ai.timefold.solver.core.config.solver.SolverConfig;
import ai.timefold.solver.core.config.solver.termination.TerminationConfig;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.solverforgebench.jssp.domain.JsspSchedule;
import com.solverforgebench.jssp.domain.OperationAssignment;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class Main {

    static class OperationInput {
        @JsonProperty("job_id")
        public int jobId;
        @JsonProperty("op_index")
        public int opIndex;
        @JsonProperty("machine_id")
        public int machineId;
        public int duration;
    }

    static class InstanceInput {
        @JsonProperty("num_jobs")
        public int numJobs;
        @JsonProperty("num_machines")
        public int numMachines;
        public List<OperationInput> operations;
    }

    static class OperationOutput {
        @JsonProperty("job_id")
        public int jobId;
        @JsonProperty("op_index")
        public int opIndex;
        @JsonProperty("machine_id")
        public int machineId;
        public int start;
        public int duration;

        OperationOutput(OperationAssignment operation) {
            this.jobId = operation.getJobId();
            this.opIndex = operation.getOpIndex();
            this.machineId = operation.getMachineId();
            this.start = operation.getStart();
            this.duration = operation.getDuration();
        }
    }

    static class JsspOutput {
        public List<OperationOutput> operations;
        @JsonProperty("reported_makespan")
        public int reportedMakespan;

        JsspOutput(List<OperationOutput> operations, int reportedMakespan) {
            this.operations = operations;
            this.reportedMakespan = reportedMakespan;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java -jar timefold-jssp.jar <time_limit_seconds>");
            System.exit(1);
        }
        long timeLimitSeconds = Long.parseLong(args[0]);

        ObjectMapper mapper = new ObjectMapper()
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        InstanceInput input = mapper.readValue(System.in, InstanceInput.class);

        int horizon = input.operations.stream().mapToInt(operation -> operation.duration).sum();
        List<Integer> startRange = new ArrayList<>();
        for (int i = 0; i <= horizon; i++) {
            startRange.add(i);
        }

        List<Integer> dispatchStarts = dispatchStarts(input);
        List<OperationAssignment> operations = new ArrayList<>();
        for (int i = 0; i < input.operations.size(); i++) {
            OperationInput operation = input.operations.get(i);
            operations.add(new OperationAssignment(
                    i,
                    operation.jobId,
                    operation.opIndex,
                    operation.machineId,
                    operation.duration,
                    dispatchStarts.get(i)));
        }

        JsspSchedule problem = new JsspSchedule(startRange, operations);
        SolverConfig solverConfig = new SolverConfig()
                .withSolutionClass(JsspSchedule.class)
                .withEntityClasses(OperationAssignment.class)
                .withConstraintProviderClass(JsspConstraintProvider.class)
                .withRandomSeed(1L)
                .withMoveThreadCount(SolverConfig.MOVE_THREAD_COUNT_NONE)
                .withTerminationConfig(new TerminationConfig()
                        .withSpentLimit(java.time.Duration.ofSeconds(timeLimitSeconds)));

        SolverFactory<JsspSchedule> solverFactory = SolverFactory.create(solverConfig);
        Solver<JsspSchedule> solver = solverFactory.buildSolver();
        JsspSchedule solution = solver.solve(problem);

        List<OperationOutput> outputOperations = solution.getOperations().stream()
                .sorted(Comparator
                        .comparingInt(OperationAssignment::getJobId)
                        .thenComparingInt(OperationAssignment::getOpIndex))
                .map(OperationOutput::new)
                .toList();
        int makespan = solution.getOperations().stream()
                .mapToInt(OperationAssignment::getEnd)
                .max()
                .orElse(0);
        mapper.writeValue(System.out, new JsspOutput(outputOperations, makespan));
    }

    private static List<Integer> dispatchStarts(InstanceInput input) {
        int[] jobReady = new int[input.numJobs];
        int[] machineReady = new int[input.numMachines];
        List<Integer> starts = new ArrayList<>();
        for (OperationInput operation : input.operations) {
            int start = Math.max(jobReady[operation.jobId], machineReady[operation.machineId]);
            starts.add(start);
            int finish = start + operation.duration;
            jobReady[operation.jobId] = finish;
            machineReady[operation.machineId] = finish;
        }
        return starts;
    }
}
