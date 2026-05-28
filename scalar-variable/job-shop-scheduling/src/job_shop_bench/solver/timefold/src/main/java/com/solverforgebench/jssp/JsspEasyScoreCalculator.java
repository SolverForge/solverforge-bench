package com.solverforgebench.jssp;

import ai.timefold.solver.core.api.score.HardSoftScore;
import ai.timefold.solver.core.api.score.calculator.EasyScoreCalculator;

import com.solverforgebench.jssp.domain.JsspSchedule;

public class JsspEasyScoreCalculator implements EasyScoreCalculator<JsspSchedule, HardSoftScore> {

    @Override
    public HardSoftScore calculateScore(JsspSchedule schedule) {
        return JsspScheduleEvaluator.evaluate(schedule).score();
    }
}
