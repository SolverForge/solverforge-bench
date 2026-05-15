from pydantic import BaseModel


class ShiftType(BaseModel):
    id: str
    minimumNumberOfConsecutiveAssignments: int
    maximumNumberOfConsecutiveAssignments: int


class ForbiddenSuccession(BaseModel):
    precedingShiftType: str
    succeedingShiftTypes: list[str]


class Contract(BaseModel):
    id: str
    minimumNumberOfAssignments: int
    maximumNumberOfAssignments: int
    minimumNumberOfConsecutiveWorkingDays: int
    maximumNumberOfConsecutiveWorkingDays: int
    minimumNumberOfConsecutiveDaysOff: int
    maximumNumberOfConsecutiveDaysOff: int
    maximumNumberOfWorkingWeekends: int
    completeWeekends: int


class Nurse(BaseModel):
    id: str
    contract: str
    skills: list[str]


class DayRequirement(BaseModel):
    minimum: int
    optimal: int


class CoverRequirement(BaseModel):
    shiftType: str
    skill: str
    requirementOnMonday: DayRequirement
    requirementOnTuesday: DayRequirement
    requirementOnWednesday: DayRequirement
    requirementOnThursday: DayRequirement
    requirementOnFriday: DayRequirement
    requirementOnSaturday: DayRequirement
    requirementOnSunday: DayRequirement


class ShiftOffRequest(BaseModel):
    nurse: str
    shiftType: str
    day: str


class WeekData(BaseModel):
    scenario: str
    requirements: list[CoverRequirement]
    shiftOffRequests: list[ShiftOffRequest]


class NurseHistory(BaseModel):
    nurse: str
    numberOfAssignments: int
    numberOfWorkingWeekends: int
    lastAssignedShiftType: str
    numberOfConsecutiveAssignments: int
    numberOfConsecutiveWorkingDays: int
    numberOfConsecutiveDaysOff: int


class History(BaseModel):
    week: int
    scenario: str
    nurseHistory: list[NurseHistory]


class Scenario(BaseModel):
    id: str
    numberOfWeeks: int
    skills: list[str]
    shiftTypes: list[ShiftType]
    forbiddenShiftTypeSuccessions: list[ForbiddenSuccession]
    contracts: list[Contract]
    nurses: list[Nurse]


class Instance(BaseModel):
    """Static INRC-II instance: scenario + initial history + all week data."""

    scenario: Scenario
    history: History
    weeks: list[WeekData]


class Assignment(BaseModel):
    nurse: str
    day: str
    shiftType: str
    skill: str


class Solution(BaseModel):
    assignments: list[list[Assignment]]
    cost: int | None = None
    reported_cost: int | None = None
    fresh_cost: int | None = None
    score_delta: int | None = None
    score_drift: bool | None = None
    reported_score: str | None = None
    fresh_score: str | None = None
    solver_metadata: dict | None = None
    validator_cost: int | None = None
    validator_breakdown: dict[str, int] | None = None
    validator_model_delta: int | None = None
    solution_artifact: str | None = None
