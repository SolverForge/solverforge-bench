package com.solverforgebench.hospital;

import ai.timefold.solver.core.api.score.HardSoftScore;
import ai.timefold.solver.core.api.solver.SolutionManager;
import ai.timefold.solver.core.api.solver.Solver;
import ai.timefold.solver.core.api.solver.SolverFactory;
import ai.timefold.solver.core.config.solver.SolverConfig;
import ai.timefold.solver.core.config.solver.termination.TerminationConfig;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.solverforgebench.hospital.domain.Employee;
import com.solverforgebench.hospital.domain.HospitalSchedule;
import com.solverforgebench.hospital.domain.Shift;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

/** Reads the shared solver-input document on stdin, solves, writes JSON to stdout. */
public class Main {

    static class EmployeeInput {
        @JsonProperty("home_hub")
        public int homeHub;
        public int[] skills;
        @JsonProperty("unavailable_days")
        public long[] unavailableDays;
        @JsonProperty("desired_days")
        public long[] desiredDays;
        @JsonProperty("undesired_days")
        public long[] undesiredDays;
    }

    static class ShiftInput {
        public long start;
        public long end;
        public int hub;
        @JsonProperty("required_skill")
        public int requiredSkill;
    }

    static class InstanceInput {
        @JsonProperty("skill_hubs")
        public List<Integer> skillHubs;
        @JsonProperty("skill_candidates")
        public List<int[]> skillCandidates;
        public List<EmployeeInput> employees;
        public List<ShiftInput> shifts;
    }

    static class FairStartWitness {
        @JsonProperty("adapter_hint_count")
        public int adapterHintCount = 0;
        @JsonProperty("preliminary_solve_count")
        public int preliminarySolveCount = 0;
        @JsonProperty("fallback_solution_enabled")
        public boolean fallbackSolutionEnabled = false;
        @JsonProperty("preassigned_scalar_variables")
        public int preassignedScalarVariables;
        @JsonProperty("prefilled_list_variables")
        public int prefilledListVariables = 0;

        FairStartWitness(int preassignedScalarVariables) {
            this.preassignedScalarVariables = preassignedScalarVariables;
        }
    }

    static class Output {
        public List<Integer> assignments;
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
            System.err.println("Usage: java -jar timefold-hospital-scale.jar <time_limit_seconds>");
            System.exit(1);
        }
        long timeLimitSeconds = Long.parseLong(args[0]);

        ObjectMapper mapper = new ObjectMapper()
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        InstanceInput input = mapper.readValue(System.in, InstanceInput.class);

        List<Employee> employees = new ArrayList<>(input.employees.size());
        for (int index = 0; index < input.employees.size(); index++) {
            EmployeeInput employee = input.employees.get(index);
            employees.add(new Employee(
                    index,
                    employee.homeHub,
                    employee.skills,
                    employee.unavailableDays,
                    employee.desiredDays,
                    employee.undesiredDays));
        }

        // One shared candidate list per skill: the identical domain the
        // SolverForge model receives.
        List<List<Employee>> rangeBySkill = new ArrayList<>(input.skillCandidates.size());
        for (int[] candidates : input.skillCandidates) {
            List<Employee> range = new ArrayList<>(candidates.length);
            for (int employeeIndex : candidates) {
                range.add(employees.get(employeeIndex));
            }
            rangeBySkill.add(List.copyOf(range));
        }

        List<Shift> shifts = new ArrayList<>(input.shifts.size());
        for (int index = 0; index < input.shifts.size(); index++) {
            ShiftInput shift = input.shifts.get(index);
            shifts.add(new Shift(
                    index,
                    shift.start,
                    shift.end,
                    shift.hub,
                    shift.requiredSkill,
                    rangeBySkill.get(shift.requiredSkill)));
        }

        HospitalSchedule problem = new HospitalSchedule(employees, shifts);
        FairStartWitness fairStartWitness = new FairStartWitness(preassigned(problem));

        SolverConfig solverConfig = new SolverConfig()
                .withSolutionClass(HospitalSchedule.class)
                .withEntityClasses(Shift.class)
                .withConstraintProviderClass(HospitalConstraintProvider.class)
                .withRandomSeed(1L)
                .withMoveThreadCount(SolverConfig.MOVE_THREAD_COUNT_NONE)
                .withTerminationConfig(new TerminationConfig()
                        .withSpentLimit(Duration.ofSeconds(timeLimitSeconds)));
        SolverFactory<HospitalSchedule> solverFactory = SolverFactory.create(solverConfig);
        Solver<HospitalSchedule> solver = solverFactory.buildSolver();
        HospitalSchedule solution = solver.solve(problem);

        HardSoftScore reported = solution.getScore();
        SolutionManager<HospitalSchedule, HardSoftScore> solutionManager = SolutionManager.create(solverFactory);
        HardSoftScore fresh = solutionManager.update(solution);

        Output output = new Output();
        output.assignments = new ArrayList<>(solution.getShifts().size());
        for (Shift shift : solution.getShifts()) {
            output.assignments.add(shift.getEmployee() == null ? null : shift.getEmployee().getIndex());
        }
        output.reportedCost = reported == null ? null : -reported.softScore();
        output.freshCost = fresh == null ? null : -fresh.softScore();
        output.hardViolations = fresh == null ? null : -fresh.hardScore();
        output.reportedScore = reported == null ? null : reported.toString();
        output.freshScore = fresh == null ? null : fresh.toString();
        output.fairStartWitness = fairStartWitness;
        mapper.writeValue(System.out, output);
    }

    private static int preassigned(HospitalSchedule problem) {
        int preassigned = 0;
        for (Shift shift : problem.getShifts()) {
            if (shift.getEmployee() != null) {
                preassigned++;
            }
        }
        return preassigned;
    }
}
