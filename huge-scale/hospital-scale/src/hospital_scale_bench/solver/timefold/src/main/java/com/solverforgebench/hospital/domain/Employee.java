package com.solverforgebench.hospital.domain;

import java.util.Arrays;

/** Staff member: a problem fact the solver reads but never moves. */
public class Employee {

    public static final long MINUTES_PER_DAY = 1440L;

    private final int index;
    private final int homeHub;
    private final int[] skills;
    private final long[] unavailableDays;
    private final long[] desiredDays;
    private final long[] undesiredDays;

    public Employee(
            int index,
            int homeHub,
            int[] skills,
            long[] unavailableDays,
            long[] desiredDays,
            long[] undesiredDays) {
        this.index = index;
        this.homeHub = homeHub;
        this.skills = skills.clone();
        Arrays.sort(this.skills);
        this.unavailableDays = unavailableDays.clone();
        this.desiredDays = desiredDays.clone();
        this.undesiredDays = undesiredDays.clone();
    }

    public int getIndex() {
        return index;
    }

    public int getHomeHub() {
        return homeHub;
    }

    public boolean hasSkill(int skill) {
        return Arrays.binarySearch(skills, skill) >= 0;
    }

    public long unavailableMinutes(Shift shift) {
        long minutes = 0;
        for (long day : unavailableDays) {
            minutes += shift.minutesOn(day);
        }
        return minutes;
    }

    public long desiredCount(Shift shift) {
        return touchedCount(shift, desiredDays);
    }

    public long undesiredCount(Shift shift) {
        return touchedCount(shift, undesiredDays);
    }

    private static long touchedCount(Shift shift, long[] days) {
        long count = 0;
        for (long day : days) {
            if (shift.touches(day)) {
                count++;
            }
        }
        return count;
    }

    @Override
    public String toString() {
        return "Employee-" + index;
    }
}
