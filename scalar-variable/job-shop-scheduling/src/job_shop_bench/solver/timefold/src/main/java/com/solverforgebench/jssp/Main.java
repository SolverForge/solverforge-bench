package com.solverforgebench.jssp;

import ai.timefold.solver.core.api.solver.Solver;
import ai.timefold.solver.core.api.solver.SolverFactory;
import ai.timefold.solver.core.config.solver.SolverConfig;
import ai.timefold.solver.core.config.solver.termination.TerminationConfig;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.solverforgebench.jssp.domain.JsspSchedule;
import com.solverforgebench.jssp.domain.MachineSequence;
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
            this.start = operation.getStart() == null ? 0 : operation.getStart();
            this.duration = operation.getDuration();
        }
    }

    static class JsspOutput {
        public List<OperationOutput> operations;
        @JsonProperty("reported_makespan")
        public int reportedMakespan;
        @JsonProperty("fair_start_witness")
        public FairStartWitness fairStartWitness;

        JsspOutput(List<OperationOutput> operations, int reportedMakespan, FairStartWitness fairStartWitness) {
            this.operations = operations;
            this.reportedMakespan = reportedMakespan;
            this.fairStartWitness = fairStartWitness;
        }
    }

    static class FairStartWitness {
        @JsonProperty("adapter_hint_count")
        public int adapterHintCount = 0;
        @JsonProperty("preliminary_solve_count")
        public int preliminarySolveCount = 0;
        @JsonProperty("fallback_solution_enabled")
        public boolean fallbackSolutionEnabled = false;
        @JsonProperty("preassigned_scalar_variables")
        public int preassignedScalarVariables = 0;
        @JsonProperty("prefilled_list_variables")
        public int prefilledListVariables;

        FairStartWitness(int prefilledListVariables) {
            this.prefilledListVariables = prefilledListVariables;
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

        List<OperationAssignment> operations = new ArrayList<>();
        for (int i = 0; i < input.operations.size(); i++) {
            OperationInput operation = input.operations.get(i);
            operations.add(new OperationAssignment(
                    i,
                    operation.jobId,
                    operation.opIndex,
                    operation.machineId,
                    operation.duration));
        }

        List<List<OperationAssignment>> operationsByMachine = new ArrayList<>();
        for (int i = 0; i < input.numMachines; i++) {
            operationsByMachine.add(new ArrayList<>());
        }
        for (OperationAssignment operation : operations) {
            if (operation.getMachineId() >= 0 && operation.getMachineId() < input.numMachines) {
                operationsByMachine.get(operation.getMachineId()).add(operation);
            }
        }

        List<MachineSequence> machineSequences = new ArrayList<>();
        for (int i = 0; i < input.numMachines; i++) {
            machineSequences.add(new MachineSequence(i, operationsByMachine.get(i)));
        }

        JsspSchedule problem = new JsspSchedule(
                input.numJobs,
                input.numMachines,
                machineSequences,
                operations);
        FairStartWitness fairStartWitness = fairStartWitness(problem);
        SolverConfig solverConfig = new SolverConfig()
                .withSolutionClass(JsspSchedule.class)
                .withEntityClasses(MachineSequence.class, OperationAssignment.class)
                .withEasyScoreCalculatorClass(JsspEasyScoreCalculator.class)
                .withRandomSeed(1L)
                .withMoveThreadCount(SolverConfig.MOVE_THREAD_COUNT_NONE)
                .withTerminationConfig(new TerminationConfig()
                        .withSpentLimit(java.time.Duration.ofSeconds(timeLimitSeconds)));

        SolverFactory<JsspSchedule> solverFactory = SolverFactory.create(solverConfig);
        Solver<JsspSchedule> solver = solverFactory.buildSolver();
        JsspSchedule solution = solver.solve(problem);

        JsspScheduleEvaluator.Evaluation evaluation = JsspScheduleEvaluator.evaluate(solution);
        for (OperationAssignment operation : solution.getOperations()) {
            operation.setStart(evaluation.startFor(operation));
        }
        List<OperationOutput> outputOperations = solution.getOperations().stream()
                .sorted(Comparator
                        .comparingInt(OperationAssignment::getJobId)
                .thenComparingInt(OperationAssignment::getOpIndex))
                .map(OperationOutput::new)
                .toList();
        mapper.writeValue(System.out, new JsspOutput(outputOperations, evaluation.makespan(), fairStartWitness));
    }

    private static FairStartWitness fairStartWitness(JsspSchedule problem) {
        int prefilled = 0;
        for (MachineSequence machine : problem.getMachineSequences()) {
            if (!machine.getOperations().isEmpty()) {
                prefilled++;
            }
        }
        return new FairStartWitness(prefilled);
    }
}
