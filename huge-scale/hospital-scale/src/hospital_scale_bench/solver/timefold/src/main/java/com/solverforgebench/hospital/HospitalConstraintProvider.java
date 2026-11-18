package com.solverforgebench.hospital;

import ai.timefold.solver.core.api.score.HardSoftScore;
import ai.timefold.solver.core.api.score.stream.Constraint;
import ai.timefold.solver.core.api.score.stream.ConstraintCollectors;
import ai.timefold.solver.core.api.score.stream.ConstraintFactory;
import ai.timefold.solver.core.api.score.stream.ConstraintProvider;
import ai.timefold.solver.core.api.score.stream.Joiners;

import com.solverforgebench.hospital.domain.Shift;

/**
 * The hospital ruleset. Weights mirror the SolverForge model and the benchmark
 * validator exactly; scripts/verify_model_parity.py pins them.
 */
public class HospitalConstraintProvider implements ConstraintProvider {

    static final long ASSIGNED_SHIFT_HARD = 1L;
    static final long REQUIRED_SKILL_HARD = 10L;
    static final long STRUCTURAL_MINUTE_HARD = 20L;
    static final long ONE_SHIFT_PER_DAY_HARD = 20L;
    static final long MINIMUM_REST_MINUTES = 600L;
    static final long PREFERENCE_SOFT = 10L;

    @Override
    public Constraint[] defineConstraints(ConstraintFactory factory) {
        return new Constraint[]{
                assignedShift(factory),
                requiredSkill(factory),
                overlappingShift(factory),
                minimumRest(factory),
                oneShiftPerDay(factory),
                unavailableEmployee(factory),
                undesiredDay(factory),
                desiredDay(factory),
                balanceAssignments(factory),
        };
    }

    Constraint assignedShift(ConstraintFactory factory) {
        return factory.forEachIncludingUnassigned(Shift.class)
                .filter(shift -> shift.getEmployee() == null)
                .penalize(HardSoftScore.ofHard(ASSIGNED_SHIFT_HARD))
                .asConstraint("assigned_shift");
    }

    Constraint requiredSkill(ConstraintFactory factory) {
        return factory.forEach(Shift.class)
                .filter(shift -> !shift.getEmployee().hasSkill(shift.getRequiredSkill()))
                .penalize(HardSoftScore.ofHard(REQUIRED_SKILL_HARD))
                .asConstraint("required_skill");
    }

    Constraint overlappingShift(ConstraintFactory factory) {
        return factory.forEachUniquePair(Shift.class, Joiners.equal(Shift::getEmployee))
                .filter((left, right) -> overlapMinutes(left, right) > 0)
                .penalize(HardSoftScore.ofHard(STRUCTURAL_MINUTE_HARD), HospitalConstraintProvider::overlapMinutes)
                .asConstraint("overlapping_shift");
    }

    Constraint minimumRest(ConstraintFactory factory) {
        return factory.forEachUniquePair(Shift.class, Joiners.equal(Shift::getEmployee))
                .filter((left, right) -> restShortfall(left, right) > 0)
                .penalize(HardSoftScore.ofHard(STRUCTURAL_MINUTE_HARD), HospitalConstraintProvider::restShortfall)
                .asConstraint("minimum_rest");
    }

    Constraint oneShiftPerDay(ConstraintFactory factory) {
        return factory.forEachUniquePair(Shift.class, Joiners.equal(Shift::getEmployee))
                .filter((left, right) -> left.getFirstDay() <= right.getLastDay()
                        && right.getFirstDay() <= left.getLastDay())
                .penalize(HardSoftScore.ofHard(ONE_SHIFT_PER_DAY_HARD))
                .asConstraint("one_shift_per_day");
    }

    Constraint unavailableEmployee(ConstraintFactory factory) {
        return factory.forEach(Shift.class)
                .filter(shift -> shift.getEmployee().unavailableMinutes(shift) > 0)
                .penalize(HardSoftScore.ofHard(STRUCTURAL_MINUTE_HARD),
                        shift -> shift.getEmployee().unavailableMinutes(shift))
                .asConstraint("unavailable_employee");
    }

    Constraint undesiredDay(ConstraintFactory factory) {
        return factory.forEach(Shift.class)
                .filter(shift -> shift.getEmployee().undesiredCount(shift) > 0)
                .penalize(HardSoftScore.ofSoft(PREFERENCE_SOFT),
                        shift -> shift.getEmployee().undesiredCount(shift))
                .asConstraint("undesired_day");
    }

    Constraint desiredDay(ConstraintFactory factory) {
        return factory.forEach(Shift.class)
                .filter(shift -> shift.getEmployee().desiredCount(shift) > 0)
                .reward(HardSoftScore.ofSoft(PREFERENCE_SOFT),
                        shift -> shift.getEmployee().desiredCount(shift))
                .asConstraint("desired_day");
    }

    Constraint balanceAssignments(ConstraintFactory factory) {
        return factory.forEach(Shift.class)
                .groupBy(Shift::getEmployee, ConstraintCollectors.count())
                .penalize(HardSoftScore.ONE_SOFT, (employee, assigned) -> assigned * assigned)
                .asConstraint("balance_assignments");
    }

    static long overlapMinutes(Shift left, Shift right) {
        return Math.max(0L, Math.min(left.getEnd(), right.getEnd()) - Math.max(left.getStart(), right.getStart()));
    }

    /** Minutes short of the 10-hour rest between two non-overlapping shifts. */
    static long restShortfall(Shift left, Shift right) {
        long gap;
        if (left.getEnd() <= right.getStart()) {
            gap = right.getStart() - left.getEnd();
        } else if (right.getEnd() <= left.getStart()) {
            gap = left.getStart() - right.getEnd();
        } else {
            return 0L;
        }
        return Math.max(0L, MINIMUM_REST_MINUTES - gap);
    }
}
