package com.solverforgebench.hospital.domain;

import ai.timefold.solver.core.api.domain.common.PlanningId;
import ai.timefold.solver.core.api.domain.entity.PlanningEntity;
import ai.timefold.solver.core.api.domain.valuerange.ValueRangeProvider;
import ai.timefold.solver.core.api.domain.variable.PlanningVariable;

import java.util.List;

/** Work item that needs exactly one employee; the only planning entity. */
@PlanningEntity
public class Shift {

    @PlanningId
    private int index;
    private long start;
    private long end;
    private long firstDay;
    private long lastDay;
    private int hub;
    private int requiredSkill;
    private List<Employee> employeeRange;

    @PlanningVariable(valueRangeProviderRefs = "employeeRange", allowsUnassigned = true)
    private Employee employee;

    public Shift() {
    }

    public Shift(int index, long start, long end, int hub, int requiredSkill, List<Employee> employeeRange) {
        this.index = index;
        this.start = start;
        this.end = end;
        this.firstDay = Math.floorDiv(start, Employee.MINUTES_PER_DAY);
        this.lastDay = Math.floorDiv(end - 1, Employee.MINUTES_PER_DAY);
        this.hub = hub;
        this.requiredSkill = requiredSkill;
        this.employeeRange = employeeRange;
    }

    public int getIndex() {
        return index;
    }

    public long getStart() {
        return start;
    }

    public long getEnd() {
        return end;
    }

    public long getFirstDay() {
        return firstDay;
    }

    public long getLastDay() {
        return lastDay;
    }

    public int getHub() {
        return hub;
    }

    public int getRequiredSkill() {
        return requiredSkill;
    }

    @ValueRangeProvider(id = "employeeRange")
    public List<Employee> getEmployeeRange() {
        return employeeRange;
    }

    public Employee getEmployee() {
        return employee;
    }

    public void setEmployee(Employee employee) {
        this.employee = employee;
    }

    /** Whether the shift touches calendar day {@code day} for at least one minute. */
    public boolean touches(long day) {
        return firstDay <= day && day <= lastDay;
    }

    /** Minutes of the shift that fall inside calendar day {@code day}. */
    public long minutesOn(long day) {
        long dayStart = day * Employee.MINUTES_PER_DAY;
        long dayEnd = dayStart + Employee.MINUTES_PER_DAY;
        return Math.max(0L, Math.min(end, dayEnd) - Math.max(start, dayStart));
    }

    @Override
    public String toString() {
        return "Shift-" + index;
    }
}
