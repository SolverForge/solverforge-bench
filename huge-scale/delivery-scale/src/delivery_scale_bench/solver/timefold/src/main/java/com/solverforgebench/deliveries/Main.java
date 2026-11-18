package com.solverforgebench.deliveries;

import ai.timefold.solver.core.api.score.HardSoftScore;
import ai.timefold.solver.core.api.solver.SolutionManager;
import ai.timefold.solver.core.api.solver.Solver;
import ai.timefold.solver.core.api.solver.SolverFactory;
import ai.timefold.solver.core.config.solver.SolverConfig;
import ai.timefold.solver.core.config.solver.termination.TerminationConfig;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.solverforgebench.deliveries.domain.Delivery;
import com.solverforgebench.deliveries.domain.DeliverySchedule;
import com.solverforgebench.deliveries.domain.Depot;
import com.solverforgebench.deliveries.domain.Vehicle;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

/** Reads the shared solver-input document on stdin, solves, writes JSON to stdout. */
public class Main {

    static class InstanceInput {
        @JsonProperty("speed_mps")
        public double speedMps;
        public long[] depot;
        @JsonProperty("departure_time")
        public long departureTime;
        @JsonProperty("vehicle_count")
        public int vehicleCount;
        public long capacity;
        public long[] xs;
        public long[] ys;
        public long[] demands;
        @JsonProperty("min_starts")
        public long[] minStarts;
        @JsonProperty("max_ends")
        public long[] maxEnds;
        public long[] services;
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

    static class Output {
        public List<List<Integer>> routes;
        @JsonProperty("reported_cost")
        public Long reportedCost;
        @JsonProperty("fresh_cost")
        public Long freshCost;
        @JsonProperty("hard_violations")
        public Long hardViolations;
        @JsonProperty("reported_score")
        public String reportedScore;
        @JsonProperty("fresh_score")
        public String freshScore;
        @JsonProperty("fair_start_witness")
        public FairStartWitness fairStartWitness;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java -jar timefold-delivery-scale.jar <time_limit_seconds>");
            System.exit(1);
        }
        long timeLimitSeconds = Long.parseLong(args[0]);

        ObjectMapper mapper = new ObjectMapper()
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        InstanceInput input = mapper.readValue(System.in, InstanceInput.class);

        Depot.useSpeed(input.speedMps);
        Depot depot = new Depot(input.depot[0], input.depot[1], input.departureTime, input.capacity);
        List<Delivery> deliveries = new ArrayList<>(input.xs.length);
        for (int index = 0; index < input.xs.length; index++) {
            deliveries.add(new Delivery(
                    index,
                    input.xs[index],
                    input.ys[index],
                    input.demands[index],
                    input.minStarts[index],
                    input.maxEnds[index],
                    input.services[index]));
        }
        List<Vehicle> vehicles = new ArrayList<>(input.vehicleCount);
        for (int index = 0; index < input.vehicleCount; index++) {
            vehicles.add(new Vehicle(index, depot));
        }

        DeliverySchedule problem = new DeliverySchedule(deliveries, vehicles);
        FairStartWitness fairStartWitness = new FairStartWitness(prefilled(problem));

        SolverConfig solverConfig = new SolverConfig()
                .withSolutionClass(DeliverySchedule.class)
                .withEntityClasses(Vehicle.class, Delivery.class)
                .withConstraintProviderClass(DeliveryConstraintProvider.class)
                .withRandomSeed(1L)
                .withMoveThreadCount(SolverConfig.MOVE_THREAD_COUNT_NONE)
                .withTerminationConfig(new TerminationConfig()
                        .withSpentLimit(Duration.ofSeconds(timeLimitSeconds)));
        SolverFactory<DeliverySchedule> solverFactory = SolverFactory.create(solverConfig);
        Solver<DeliverySchedule> solver = solverFactory.buildSolver();
        DeliverySchedule solution = solver.solve(problem);

        HardSoftScore reported = solution.getScore();
        SolutionManager<DeliverySchedule, HardSoftScore> solutionManager = SolutionManager.create(solverFactory);
        HardSoftScore fresh = solutionManager.update(solution);

        Output output = new Output();
        output.routes = new ArrayList<>(solution.getVehicles().size());
        for (Vehicle vehicle : solution.getVehicles()) {
            List<Integer> route = new ArrayList<>(vehicle.getDeliveries().size());
            for (Delivery delivery : vehicle.getDeliveries()) {
                route.add(delivery.getIndex());
            }
            output.routes.add(route);
        }
        output.reportedCost = reported == null ? null : -reported.softScore();
        output.freshCost = fresh == null ? null : -fresh.softScore();
        output.hardViolations = fresh == null ? null : -fresh.hardScore();
        output.reportedScore = reported == null ? null : reported.toString();
        output.freshScore = fresh == null ? null : fresh.toString();
        output.fairStartWitness = fairStartWitness;
        mapper.writeValue(System.out, output);
    }

    private static int prefilled(DeliverySchedule problem) {
        int prefilled = 0;
        for (Vehicle vehicle : problem.getVehicles()) {
            if (!vehicle.getDeliveries().isEmpty()) {
                prefilled++;
            }
        }
        return prefilled;
    }
}
