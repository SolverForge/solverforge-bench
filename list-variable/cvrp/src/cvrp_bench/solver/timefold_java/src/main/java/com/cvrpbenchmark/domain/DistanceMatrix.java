package com.cvrpbenchmark.domain;

import ai.timefold.solver.core.api.domain.solution.ProblemFactProperty;

public class DistanceMatrix {

    private final int[][] matrix;

    public DistanceMatrix(int[][] matrix) {
        this.matrix = matrix;
    }

    public int getDistance(int from, int to) {
        return matrix[from][to];
    }

    public int[][] getMatrix() {
        return matrix;
    }
}
