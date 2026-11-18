package com.solverforgebench.deliveries.domain;

/** The single depot every vehicle leaves from and returns to. */
public record Depot(long x, long y, long departureTime, long capacity) {

    /** Set once from the solver input before any route is scored. */
    private static double speed = 10.0;

    public static void useSpeed(double speedMps) {
        speed = speedMps;
    }

    /** Euclidean distance over the speed, rounded half up to whole seconds. */
    public static long travelSeconds(long ax, long ay, long bx, long by) {
        long dx = ax - bx;
        long dy = ay - by;
        return (long) Math.floor(Math.sqrt((double) (dx * dx + dy * dy)) / speed + 0.5);
    }
}
