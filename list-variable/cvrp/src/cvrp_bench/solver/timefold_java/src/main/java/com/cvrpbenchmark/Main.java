package com.cvrpbenchmark;

import ai.timefold.solver.core.api.solver.Solver;
import ai.timefold.solver.core.api.solver.SolverFactory;
import ai.timefold.solver.core.config.solver.SolverConfig;
import ai.timefold.solver.core.config.solver.termination.TerminationConfig;

import com.cvrpbenchmark.domain.DistanceMatrix;
import com.cvrpbenchmark.domain.Vehicle;
import com.cvrpbenchmark.domain.Visit;
import com.cvrpbenchmark.domain.VehicleRoutePlan;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.List;

public class Main {

    static class CvrpInput {
        public int dimension;
        public int capacity;
        public int[] demand;
        public int depot;
        @JsonProperty("distance_matrix")
        public int[][] distanceMatrix;
    }

    static class CvrpOutput {
        public List<List<Integer>> routes;
        public int cost;

        CvrpOutput(List<List<Integer>> routes, int cost) {
            this.routes = routes;
            this.cost = cost;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java -jar timefold-cvrp.jar <time_limit_seconds>");
            System.exit(1);
        }
        long timeLimitSeconds = Long.parseLong(args[0]);

        ObjectMapper mapper = new ObjectMapper();
        CvrpInput input = mapper.readValue(System.in, CvrpInput.class);

        int n = input.demand.length;
        int numVehicles = n - 1;  // one vehicle per customer slot (indices 1..n-1)

        List<Vehicle> vehicles = new ArrayList<>(numVehicles);
        for (int i = 1; i <= numVehicles; i++) {
            vehicles.add(new Vehicle("vehicle_" + i, input.capacity, input.depot));
        }

        List<Visit> visits = new ArrayList<>(numVehicles);
        for (int i = 1; i < n; i++) {
            visits.add(new Visit(i, i, input.demand[i]));
        }

        DistanceMatrix distanceMatrix = new DistanceMatrix(input.distanceMatrix);
        VehicleRoutePlan problem = new VehicleRoutePlan(vehicles, visits, distanceMatrix);

        SolverConfig solverConfig = new SolverConfig()
                .withSolutionClass(VehicleRoutePlan.class)
                .withEntityClasses(Vehicle.class, Visit.class)
                .withConstraintProviderClass(CvrpConstraintProvider.class)
                .withTerminationConfig(new TerminationConfig()
                        .withSpentLimit(java.time.Duration.ofSeconds(timeLimitSeconds)));

        SolverFactory<VehicleRoutePlan> solverFactory = SolverFactory.create(solverConfig);
        Solver<VehicleRoutePlan> solver = solverFactory.buildSolver();
        VehicleRoutePlan solution = solver.solve(problem);

        List<List<Integer>> routes = new ArrayList<>();
        for (Vehicle vehicle : solution.getVehicles()) {
            if (!vehicle.getVisits().isEmpty()) {
                List<Integer> route = new ArrayList<>();
                for (Visit visit : vehicle.getVisits()) {
                    route.add(visit.getId());
                }
                routes.add(route);
            }
        }
        int cost = -solution.getScore().softScore();

        mapper.writeValue(System.out, new CvrpOutput(routes, cost));
    }
}
