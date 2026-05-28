package com.solverforgebench.nrp;

import ai.timefold.solver.core.api.solver.Solver;
import ai.timefold.solver.core.api.solver.SolverFactory;
import ai.timefold.solver.core.config.solver.SolverConfig;
import ai.timefold.solver.core.config.solver.termination.TerminationConfig;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.solverforgebench.nrp.domain.NurseFact;
import com.solverforgebench.nrp.domain.NurseRoster;
import com.solverforgebench.nrp.domain.ShiftAssignment;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;

public class Main {

    static class NurseInput {
        public String id;
        @JsonProperty("contract_idx")
        public int contractIdx;
        public List<Integer> skills;
    }

    static class ContractInput {
        public String id;
        @JsonProperty("min_assignments")
        public int minAssignments;
        @JsonProperty("max_assignments")
        public int maxAssignments;
        @JsonProperty("min_consecutive_working")
        public int minConsecutiveWorking;
        @JsonProperty("max_consecutive_working")
        public int maxConsecutiveWorking;
        @JsonProperty("min_consecutive_off")
        public int minConsecutiveOff;
        @JsonProperty("max_consecutive_off")
        public int maxConsecutiveOff;
        @JsonProperty("max_working_weekends")
        public int maxWorkingWeekends;
        @JsonProperty("complete_weekends")
        public boolean completeWeekends;
    }

    static class ShiftTypeInput {
        public String id;
        @JsonProperty("min_consecutive")
        public int minConsecutive;
        @JsonProperty("max_consecutive")
        public int maxConsecutive;
    }

    static class ShiftInput {
        public int week;
        public int day;
        @JsonProperty("shift_type_idx")
        public int shiftTypeIdx;
        @JsonProperty("skill_idx")
        public int skillIdx;
        @JsonProperty("is_minimum")
        public boolean minimum;
    }

    static class ForbiddenInput {
        public int preceding;
        public List<Integer> succeeding;
    }

    static class NurseHistoryInput {
        @JsonProperty("nurse_idx")
        public int nurseIdx;
        @JsonProperty("num_assignments")
        public int numAssignments;
        @JsonProperty("num_working_weekends")
        public int numWorkingWeekends;
        @JsonProperty("last_shift_type_idx")
        public Integer lastShiftTypeIdx;
        @JsonProperty("num_consecutive_assignments")
        public int numConsecutiveAssignments;
        @JsonProperty("num_consecutive_working")
        public int numConsecutiveWorking;
        @JsonProperty("num_consecutive_off")
        public int numConsecutiveOff;
    }

    static class ShiftOffInput {
        @JsonProperty("nurse_idx")
        public int nurseIdx;
        @JsonProperty("global_day")
        public int globalDay;
        @JsonProperty("shift_type_idx")
        public BigInteger shiftTypeIdx;
    }

    static class InstanceInput {
        public List<NurseInput> nurses;
        public List<ContractInput> contracts;
        @JsonProperty("shift_types")
        public List<ShiftTypeInput> shiftTypes;
        public List<ForbiddenInput> forbidden;
        @JsonProperty("shift_off_requests")
        public List<ShiftOffInput> shiftOffRequests;
        @JsonProperty("nurse_history")
        public List<NurseHistoryInput> nurseHistory;
        public List<ShiftInput> shifts;
        @JsonProperty("num_weeks")
        public int numWeeks;
        @JsonProperty("skill_names")
        public List<String> skillNames;
        @JsonProperty("shift_type_names")
        public List<String> shiftTypeNames;
        @JsonProperty("nurse_names")
        public List<String> nurseNames;
    }

    static class AssignmentOutput {
        public String nurse;
        public String day;
        public String shiftType;
        public String skill;

        AssignmentOutput(String nurse, String day, String shiftType, String skill) {
            this.nurse = nurse;
            this.day = day;
            this.shiftType = shiftType;
            this.skill = skill;
        }
    }

    static class NrpOutput {
        public List<List<AssignmentOutput>> assignments;
        public int cost;
        @JsonProperty("fair_start_witness")
        public FairStartWitness fairStartWitness;

        NrpOutput(List<List<AssignmentOutput>> assignments, int cost, FairStartWitness fairStartWitness) {
            this.assignments = assignments;
            this.cost = cost;
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
        public int preassignedScalarVariables;
        @JsonProperty("prefilled_list_variables")
        public int prefilledListVariables = 0;

        FairStartWitness(int preassignedScalarVariables) {
            this.preassignedScalarVariables = preassignedScalarVariables;
        }
    }

    private static final String[] DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"};
    private static final BigInteger ANY_SHIFT_TYPE = BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE);

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java -jar timefold-nrp.jar <time_limit_seconds>");
            System.exit(1);
        }
        long timeLimitSeconds = Long.parseLong(args[0]);

        ObjectMapper mapper = new ObjectMapper()
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        InstanceInput input = mapper.readValue(System.in, InstanceInput.class);
        int totalDays = input.numWeeks * 7;

        int[] shiftTypeMinConsecutive = new int[input.shiftTypes.size()];
        int[] shiftTypeMaxConsecutive = new int[input.shiftTypes.size()];
        for (int i = 0; i < input.shiftTypes.size(); i++) {
            ShiftTypeInput shiftType = input.shiftTypes.get(i);
            shiftTypeMinConsecutive[i] = shiftType.minConsecutive;
            shiftTypeMaxConsecutive[i] = shiftType.maxConsecutive;
        }

        NurseHistoryInput[] historyByNurse = new NurseHistoryInput[input.nurses.size()];
        for (NurseHistoryInput history : input.nurseHistory) {
            historyByNurse[history.nurseIdx] = history;
        }

        List<NurseFact> nurses = new ArrayList<>();
        for (int i = 0; i < input.nurses.size(); i++) {
            NurseInput nurse = input.nurses.get(i);
            ContractInput contract = input.contracts.get(nurse.contractIdx);
            NurseHistoryInput history = historyByNurse[i];
            nurses.add(new NurseFact(
                    nurse.id,
                    i,
                    new HashSet<>(nurse.skills),
                    contract.minAssignments,
                    contract.maxAssignments,
                    contract.minConsecutiveWorking,
                    contract.maxConsecutiveWorking,
                    contract.minConsecutiveOff,
                    contract.maxConsecutiveOff,
                    contract.maxWorkingWeekends,
                    contract.completeWeekends,
                    history.numAssignments,
                    history.numWorkingWeekends,
                    history.lastShiftTypeIdx,
                    history.numConsecutiveAssignments,
                    history.numConsecutiveWorking,
                    history.numConsecutiveOff,
                    totalDays,
                    shiftTypeMinConsecutive,
                    shiftTypeMaxConsecutive));
        }
        NurseFact unassignedNurse = new NurseFact(
                "__UNASSIGNED__",
                -1,
                new HashSet<>(),
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                false,
                0,
                0,
                null,
                0,
                0,
                0,
                totalDays,
                shiftTypeMinConsecutive,
                shiftTypeMaxConsecutive);
        nurses.add(unassignedNurse);

        List<ShiftAssignment> assignments = new ArrayList<>();
        for (int i = 0; i < input.shifts.size(); i++) {
            ShiftInput shift = input.shifts.get(i);
            int globalDay = shift.week * 7 + shift.day;
            List<Integer> forbiddenPredecessors = forbiddenPredecessors(input.forbidden, shift.shiftTypeIdx);
            List<Integer> shiftOffRequestNurses = shiftOffRequestNurses(
                    input.shiftOffRequests,
                    globalDay,
                    shift.shiftTypeIdx);
            List<NurseFact> nurseRange = nurseRangeForShift(
                    nurses,
                    unassignedNurse,
                    input.forbidden,
                    globalDay,
                    shift.skillIdx,
                    shift.shiftTypeIdx,
                    shift.minimum);
            assignments.add(new ShiftAssignment(
                    i,
                    shift.week,
                    shift.day,
                    shift.shiftTypeIdx,
                    shift.skillIdx,
                    shift.minimum,
                    forbiddenPredecessors,
                    shiftOffRequestNurses,
                    nurseRange));
        }

        NurseRoster problem = new NurseRoster(nurses, assignments);
        FairStartWitness fairStartWitness = fairStartWitness(problem);
        SolverConfig solverConfig = new SolverConfig()
                .withSolutionClass(NurseRoster.class)
                .withEntityClasses(ShiftAssignment.class)
                .withConstraintProviderClass(NrpConstraintProvider.class)
                .withRandomSeed(1L)
                .withMoveThreadCount(SolverConfig.MOVE_THREAD_COUNT_NONE)
                .withTerminationConfig(new TerminationConfig()
                        .withSpentLimit(java.time.Duration.ofSeconds(timeLimitSeconds)));

        SolverFactory<NurseRoster> solverFactory = SolverFactory.create(solverConfig);
        Solver<NurseRoster> solver = solverFactory.buildSolver();
        NurseRoster solution = solver.solve(problem);

        List<List<AssignmentOutput>> weekly = new ArrayList<>();
        for (int i = 0; i < input.numWeeks; i++) {
            weekly.add(new ArrayList<>());
        }

        for (ShiftAssignment assignment : solution.getAssignments()) {
            if (assignment.getNurse() == null || assignment.getNurse().isUnassigned()) {
                continue;
            }
            weekly.get(assignment.getWeek()).add(new AssignmentOutput(
                    assignment.getNurse().getId(),
                    DAYS[assignment.getDay()],
                    input.shiftTypeNames.get(assignment.getShiftTypeIdx()),
                    input.skillNames.get(assignment.getSkillIdx())));
        }

        int cost = solution.getScore() == null ? 0 : Math.toIntExact(-solution.getScore().softScore());
        mapper.writeValue(System.out, new NrpOutput(weekly, cost, fairStartWitness));
    }

    private static FairStartWitness fairStartWitness(NurseRoster problem) {
        int preassigned = 0;
        for (ShiftAssignment assignment : problem.getAssignments()) {
            if (assignment.getNurse() != null) {
                preassigned++;
            }
        }
        return new FairStartWitness(preassigned);
    }

    private static List<Integer> forbiddenPredecessors(List<ForbiddenInput> forbidden, int shiftTypeIdx) {
        if (forbidden == null || forbidden.isEmpty()) {
            return Collections.emptyList();
        }
        List<Integer> predecessors = new ArrayList<>();
        for (ForbiddenInput entry : forbidden) {
            if (entry.succeeding != null && entry.succeeding.contains(shiftTypeIdx)) {
                predecessors.add(entry.preceding);
            }
        }
        return predecessors;
    }

    private static List<Integer> shiftOffRequestNurses(
            List<ShiftOffInput> requests,
            int globalDay,
            int shiftTypeIdx) {
        if (requests == null || requests.isEmpty()) {
            return Collections.emptyList();
        }
        List<Integer> requestNurses = new ArrayList<>();
        BigInteger shiftType = BigInteger.valueOf(shiftTypeIdx);
        for (ShiftOffInput request : requests) {
            if (request.globalDay != globalDay) {
                continue;
            }
            if (ANY_SHIFT_TYPE.equals(request.shiftTypeIdx) || shiftType.equals(request.shiftTypeIdx)) {
                requestNurses.add(request.nurseIdx);
            }
        }
        return requestNurses;
    }

    private static List<NurseFact> nurseRangeForShift(
            List<NurseFact> nurses,
            NurseFact unassignedNurse,
            List<ForbiddenInput> forbidden,
            int globalDay,
            int skillIdx,
            int shiftTypeIdx,
            boolean minimum) {
        List<NurseFact> candidates = new ArrayList<>();
        for (NurseFact nurse : nurses) {
            if (!nurse.isRealNurse()) {
                continue;
            }
            if (!nurse.getSkills().contains(skillIdx)) {
                continue;
            }
            Integer previousShift = nurse.getHistoryLastShiftTypeIdx();
            if (globalDay == 0
                    && previousShift != null
                    && forbiddenSuccessor(forbidden, previousShift, shiftTypeIdx)) {
                continue;
            }
            candidates.add(nurse);
        }
        if (!minimum) {
            candidates.add(unassignedNurse);
        }
        return candidates;
    }

    private static boolean forbiddenSuccessor(
            List<ForbiddenInput> forbidden,
            int precedingShiftTypeIdx,
            int succeedingShiftTypeIdx) {
        if (forbidden == null || forbidden.isEmpty()) {
            return false;
        }
        for (ForbiddenInput entry : forbidden) {
            if (entry.preceding == precedingShiftTypeIdx
                    && entry.succeeding != null
                    && entry.succeeding.contains(succeedingShiftTypeIdx)) {
                return true;
            }
        }
        return false;
    }
}
