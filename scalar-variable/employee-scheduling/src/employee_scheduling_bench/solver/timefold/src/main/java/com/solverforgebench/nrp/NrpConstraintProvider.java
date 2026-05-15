package com.solverforgebench.nrp;

import ai.timefold.solver.core.api.score.HardSoftScore;
import ai.timefold.solver.core.api.score.stream.Constraint;
import ai.timefold.solver.core.api.score.stream.ConstraintCollectors;
import ai.timefold.solver.core.api.score.stream.ConstraintFactory;
import ai.timefold.solver.core.api.score.stream.ConstraintProvider;
import ai.timefold.solver.core.api.score.stream.Joiners;

import com.solverforgebench.nrp.domain.NurseFact;
import com.solverforgebench.nrp.domain.ShiftAssignment;

import java.util.Arrays;
import java.util.List;

public class NrpConstraintProvider implements ConstraintProvider {

    @Override
    public Constraint[] defineConstraints(ConstraintFactory factory) {
        return new Constraint[]{
                minimumCoverage(factory),
                oneShiftPerDay(factory),
                requiredSkill(factory),
                initialForbiddenSuccession(factory),
                adjacentForbiddenSuccession(factory),
                optionalCoverage(factory),
                shiftOffRequests(factory),
                assignedNurseSoftConstraints(factory),
                unassignedNurseSoftConstraints(factory),
        };
    }

    Constraint minimumCoverage(ConstraintFactory factory) {
        return factory.forEach(ShiftAssignment.class)
                .filter(assignment -> assignment.isMinimum() && !assignment.isAssigned())
                .penalize(HardSoftScore.ONE_HARD)
                .asConstraint("minimumCoverage");
    }

    Constraint oneShiftPerDay(ConstraintFactory factory) {
        return factory.forEachUniquePair(ShiftAssignment.class,
                        Joiners.equal(ShiftAssignment::getNurse),
                        Joiners.equal(ShiftAssignment::getGlobalDay))
                .filter((left, right) -> left.isAssigned() && right.isAssigned())
                .penalize(HardSoftScore.ONE_HARD)
                .asConstraint("oneShiftPerDay");
    }

    Constraint requiredSkill(ConstraintFactory factory) {
        return factory.forEach(ShiftAssignment.class)
                .filter(ShiftAssignment::isAssigned)
                .filter(assignment -> !assignment.getNurse().getSkills().contains(assignment.getSkillIdx()))
                .penalize(HardSoftScore.ONE_HARD)
                .asConstraint("requiredSkill");
    }

    Constraint initialForbiddenSuccession(ConstraintFactory factory) {
        return factory.forEach(ShiftAssignment.class)
                .filter(assignment -> assignment.getGlobalDay() == 0 && assignment.isAssigned())
                .filter(assignment -> {
                    Integer previousShift = assignment.getNurse().getHistoryLastShiftTypeIdx();
                    return previousShift != null && assignment.hasForbiddenPredecessor(previousShift);
                })
                .penalize(HardSoftScore.ONE_HARD)
                .asConstraint("initialForbiddenSuccession");
    }

    Constraint adjacentForbiddenSuccession(ConstraintFactory factory) {
        return factory.forEachUniquePair(ShiftAssignment.class,
                        Joiners.equal(ShiftAssignment::getNurse))
                .filter((left, right) -> left.isAssigned() && right.isAssigned())
                .filter((left, right) -> Math.abs(left.getGlobalDay() - right.getGlobalDay()) == 1)
                .filter((left, right) -> {
                    ShiftAssignment previous = left.getGlobalDay() < right.getGlobalDay() ? left : right;
                    ShiftAssignment next = previous == left ? right : left;
                    return next.hasForbiddenPredecessor(previous.getShiftTypeIdx());
                })
                .penalize(HardSoftScore.ONE_HARD)
                .asConstraint("adjacentForbiddenSuccession");
    }

    Constraint optionalCoverage(ConstraintFactory factory) {
        return factory.forEach(ShiftAssignment.class)
                .filter(assignment -> !assignment.isMinimum() && !assignment.isAssigned())
                .penalize(HardSoftScore.ONE_SOFT, assignment -> 30)
                .asConstraint("optionalCoverage");
    }

    Constraint shiftOffRequests(ConstraintFactory factory) {
        return factory.forEach(ShiftAssignment.class)
                .filter(ShiftAssignment::isAssigned)
                .penalize(HardSoftScore.ONE_SOFT, ShiftAssignment::shiftOffRequestPenaltyForAssignedNurse)
                .asConstraint("shiftOffRequests");
    }

    Constraint assignedNurseSoftConstraints(ConstraintFactory factory) {
        return factory.forEach(ShiftAssignment.class)
                .filter(ShiftAssignment::isAssigned)
                .groupBy(
                        ShiftAssignment::getNurse,
                        ConstraintCollectors.toList(assignment -> new AssignedShift(
                                assignment.getGlobalDay(),
                                assignment.getShiftTypeIdx())))
                .penalize(HardSoftScore.ONE_SOFT, NrpConstraintProvider::nurseSoftPenalty)
                .asConstraint("assignedNurseSoftConstraints");
    }

    Constraint unassignedNurseSoftConstraints(ConstraintFactory factory) {
        return factory.forEach(NurseFact.class)
                .filter(NurseFact::isRealNurse)
                .ifNotExistsIncludingUnassigned(ShiftAssignment.class,
                        Joiners.equal(nurse -> nurse, ShiftAssignment::getNurse))
                .penalize(HardSoftScore.ONE_SOFT, nurse -> nurseSoftPenalty(nurse, List.of()))
                .asConstraint("unassignedNurseSoftConstraints");
    }

    private static int nurseSoftPenalty(NurseFact nurse, List<AssignedShift> assignments) {
        int totalAssignments = nurse.getHistoryAssignments() + assignments.size();
        int cost = 0;
        if (totalAssignments < nurse.getMinAssignments()) {
            cost += 20 * (nurse.getMinAssignments() - totalAssignments);
        } else if (totalAssignments > nurse.getMaxAssignments()) {
            cost += 20 * (totalAssignments - nurse.getMaxAssignments());
        }

        boolean[] works = new boolean[nurse.getTotalDays()];
        int[] shiftTypeByDay = new int[nurse.getTotalDays()];
        Arrays.fill(shiftTypeByDay, -1);
        for (AssignedShift assignment : assignments) {
            int globalDay = assignment.globalDay();
            if (globalDay < 0 || globalDay >= works.length) {
                continue;
            }
            works[globalDay] = true;
            if (shiftTypeByDay[globalDay] < 0
                    || assignment.shiftTypeIdx() < shiftTypeByDay[globalDay]) {
                shiftTypeByDay[globalDay] = assignment.shiftTypeIdx();
            }
        }

        cost += runBoundsCost(
                works,
                nurse.getHistoryLastShiftTypeIdx() != null,
                nurse.getHistoryConsecutiveWorking(),
                nurse.getMinConsecutiveWorking(),
                nurse.getMaxConsecutiveWorking(),
                30);

        boolean[] daysOff = new boolean[works.length];
        for (int i = 0; i < works.length; i++) {
            daysOff[i] = !works[i];
        }
        cost += runBoundsCost(
                daysOff,
                nurse.getHistoryLastShiftTypeIdx() == null,
                nurse.getHistoryConsecutiveOff(),
                nurse.getMinConsecutiveOff(),
                nurse.getMaxConsecutiveOff(),
                30);

        for (int shiftTypeIdx = 0; shiftTypeIdx < nurse.getShiftTypeCount(); shiftTypeIdx++) {
            boolean[] worksShiftType = new boolean[works.length];
            for (int day = 0; day < shiftTypeByDay.length; day++) {
                worksShiftType[day] = shiftTypeByDay[day] == shiftTypeIdx;
            }
            cost += runBoundsCost(
                    worksShiftType,
                    nurse.getHistoryLastShiftTypeIdx() != null
                            && nurse.getHistoryLastShiftTypeIdx() == shiftTypeIdx,
                    nurse.getHistoryConsecutiveAssignments(),
                    nurse.getShiftTypeMinConsecutive(shiftTypeIdx),
                    nurse.getShiftTypeMaxConsecutive(shiftTypeIdx),
                    15);
        }

        int workingWeekends = nurse.getHistoryWorkingWeekends();
        int weeks = works.length / 7;
        for (int week = 0; week < weeks; week++) {
            boolean saturdayWorks = works[week * 7 + 5];
            boolean sundayWorks = works[week * 7 + 6];
            if (saturdayWorks || sundayWorks) {
                workingWeekends++;
            }
            if (nurse.isCompleteWeekends() && saturdayWorks != sundayWorks) {
                cost += 30;
            }
        }
        if (workingWeekends > nurse.getMaxWorkingWeekends()) {
            cost += 30 * (workingWeekends - nurse.getMaxWorkingWeekends());
        }

        return cost;
    }

    private static int runBoundsCost(
            boolean[] active,
            boolean historyActive,
            int historyLength,
            int minLength,
            int maxLength,
            int weight) {
        int cost = 0;
        int runLength = historyActive ? historyLength : 0;
        for (boolean isActive : active) {
            if (isActive) {
                runLength++;
            } else {
                cost += closedBoundsCost(runLength, minLength, maxLength, weight);
                runLength = 0;
            }
        }
        cost += maxBoundCost(runLength, maxLength, weight);
        return cost;
    }

    private static int closedBoundsCost(int length, int minLength, int maxLength, int weight) {
        if (length == 0) {
            return 0;
        }
        int cost = 0;
        if (length < minLength) {
            cost += weight * (minLength - length);
        }
        if (length > maxLength) {
            cost += weight * (length - maxLength);
        }
        return cost;
    }

    private static int maxBoundCost(int length, int maxLength, int weight) {
        if (length > maxLength) {
            return weight * (length - maxLength);
        }
        return 0;
    }

    private record AssignedShift(int globalDay, int shiftTypeIdx) {
    }
}
