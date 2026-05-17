package com.solverforgebench.jssp;

import ai.timefold.solver.core.api.score.HardSoftScore;
import ai.timefold.solver.core.api.score.stream.Constraint;
import ai.timefold.solver.core.api.score.stream.ConstraintCollectors;
import ai.timefold.solver.core.api.score.stream.ConstraintFactory;
import ai.timefold.solver.core.api.score.stream.ConstraintProvider;
import ai.timefold.solver.core.api.score.stream.Joiners;

import com.solverforgebench.jssp.domain.OperationAssignment;

public class JsspConstraintProvider implements ConstraintProvider {

    @Override
    public Constraint[] defineConstraints(ConstraintFactory factory) {
        return new Constraint[]{
                assignedStart(factory),
                jobPrecedence(factory),
                machineNoOverlap(factory),
                makespan(factory),
        };
    }

    Constraint assignedStart(ConstraintFactory factory) {
        return factory.forEachIncludingUnassigned(OperationAssignment.class)
                .filter(operation -> !operation.isAssigned())
                .penalize(HardSoftScore.ONE_HARD)
                .asConstraint("assignedStart");
    }

    Constraint jobPrecedence(ConstraintFactory factory) {
        return factory.forEachUniquePair(OperationAssignment.class,
                        Joiners.equal(OperationAssignment::getJobId))
                .filter((left, right) -> left.isAssigned() && right.isAssigned())
                .filter((left, right) -> Math.abs(left.getOpIndex() - right.getOpIndex()) == 1)
                .penalize(HardSoftScore.ONE_HARD, JsspConstraintProvider::precedenceViolation)
                .asConstraint("jobPrecedence");
    }

    Constraint machineNoOverlap(ConstraintFactory factory) {
        return factory.forEachUniquePair(OperationAssignment.class,
                        Joiners.equal(OperationAssignment::getMachineId))
                .filter((left, right) -> left.isAssigned() && right.isAssigned())
                .filter(JsspConstraintProvider::overlaps)
                .penalize(HardSoftScore.ONE_HARD, JsspConstraintProvider::overlapAmount)
                .asConstraint("machineNoOverlap");
    }

    Constraint makespan(ConstraintFactory factory) {
        return factory.forEach(OperationAssignment.class)
                .filter(OperationAssignment::isAssigned)
                .groupBy(ConstraintCollectors.max(OperationAssignment::getEnd))
                .penalize(HardSoftScore.ONE_SOFT, value -> value == null ? 0 : value)
                .asConstraint("makespan");
    }

    private static int precedenceViolation(OperationAssignment left, OperationAssignment right) {
        OperationAssignment previous = left.getOpIndex() < right.getOpIndex() ? left : right;
        OperationAssignment next = previous == left ? right : left;
        return Math.max(0, previous.getEnd() - next.getStart());
    }

    private static boolean overlaps(OperationAssignment left, OperationAssignment right) {
        return left.getStart() < right.getEnd() && right.getStart() < left.getEnd();
    }

    private static int overlapAmount(OperationAssignment left, OperationAssignment right) {
        return Math.max(0, Math.min(left.getEnd(), right.getEnd()) - Math.max(left.getStart(), right.getStart()));
    }
}
