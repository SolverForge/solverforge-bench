import json
import re
from pathlib import Path

from employee_scheduling_bench.domain.models import (
    Assignment,
    Contract,
    CoverRequirement,
    DayRequirement,
    ForbiddenSuccession,
    History,
    Instance,
    Nurse,
    NurseHistory,
    Scenario,
    ShiftOffRequest,
    ShiftType,
    Solution,
    WeekData,
)

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_dataset_manifest(data_dir: str) -> dict:
    manifest_path = Path(data_dir) / "manifest.json"
    if not manifest_path.exists():
        return {"groups": {}}
    return json.loads(manifest_path.read_text())


def dataset_group_names(data_dir: str, group: str) -> set[str]:
    manifest = load_dataset_manifest(data_dir)
    groups = manifest.get("groups", {})
    if group not in groups:
        available = ", ".join(sorted(groups))
        raise ValueError(f"Unknown dataset set '{group}'. Available: {available}")
    return set(groups[group])


def _parse_pair(s: str) -> tuple[int, int]:
    """Parse '(a,b)' into (a, b)."""
    m = re.match(r"\((\d+),(\d+)\)", s)
    assert m, f"Cannot parse pair: {s}"
    return int(m.group(1)), int(m.group(2))


def load_scenario(path: str) -> Scenario:
    lines = Path(path).read_text().splitlines()
    idx = 0

    def skip_blank():
        nonlocal idx
        while idx < len(lines) and lines[idx].strip() == "":
            idx += 1

    # SCENARIO
    skip_blank()
    scenario_id = lines[idx].split("=")[1].strip()
    idx += 1
    skip_blank()

    # WEEKS
    num_weeks = int(lines[idx].split("=")[1].strip())
    idx += 1
    skip_blank()

    # SKILLS
    num_skills = int(lines[idx].split("=")[1].strip())
    idx += 1
    skills = []
    for _ in range(num_skills):
        skills.append(lines[idx].strip())
        idx += 1
    skip_blank()

    # SHIFT_TYPES
    num_shifts = int(lines[idx].split("=")[1].strip())
    idx += 1
    shift_types = []
    for _ in range(num_shifts):
        parts = lines[idx].strip().split()
        name = parts[0]
        min_cons, max_cons = _parse_pair(parts[1])
        shift_types.append(
            ShiftType(
                id=name,
                minimumNumberOfConsecutiveAssignments=min_cons,
                maximumNumberOfConsecutiveAssignments=max_cons,
            )
        )
        idx += 1
    skip_blank()

    # FORBIDDEN_SHIFT_TYPES_SUCCESSIONS
    assert "FORBIDDEN_SHIFT_TYPES_SUCCESSIONS" in lines[idx]
    idx += 1
    forbidden = []
    while (
        idx < len(lines)
        and lines[idx].strip()
        and not lines[idx].strip().startswith("CONTRACTS")
    ):
        parts = lines[idx].strip().split()
        preceding = parts[0]
        count = int(parts[1])
        succeeding = parts[2 : 2 + count]
        forbidden.append(
            ForbiddenSuccession(
                precedingShiftType=preceding,
                succeedingShiftTypes=succeeding,
            )
        )
        idx += 1
    skip_blank()

    # CONTRACTS
    num_contracts = int(lines[idx].split("=")[1].strip())
    idx += 1
    contracts = []
    for _ in range(num_contracts):
        parts = lines[idx].strip().split()
        name = parts[0]
        min_assign, max_assign = _parse_pair(parts[1])
        min_cons_work, max_cons_work = _parse_pair(parts[2])
        min_cons_off, max_cons_off = _parse_pair(parts[3])
        max_weekends = int(parts[4])
        complete_weekends = int(parts[5])
        contracts.append(
            Contract(
                id=name,
                minimumNumberOfAssignments=min_assign,
                maximumNumberOfAssignments=max_assign,
                minimumNumberOfConsecutiveWorkingDays=min_cons_work,
                maximumNumberOfConsecutiveWorkingDays=max_cons_work,
                minimumNumberOfConsecutiveDaysOff=min_cons_off,
                maximumNumberOfConsecutiveDaysOff=max_cons_off,
                maximumNumberOfWorkingWeekends=max_weekends,
                completeWeekends=complete_weekends,
            )
        )
        idx += 1
    skip_blank()

    # NURSES
    num_nurses = int(lines[idx].split("=")[1].strip())
    idx += 1
    nurses = []
    for _ in range(num_nurses):
        parts = lines[idx].strip().split()
        name = parts[0]
        contract = parts[1]
        num_nurse_skills = int(parts[2])
        nurse_skills = parts[3 : 3 + num_nurse_skills]
        nurses.append(Nurse(id=name, contract=contract, skills=nurse_skills))
        idx += 1

    return Scenario(
        id=scenario_id,
        numberOfWeeks=num_weeks,
        skills=skills,
        shiftTypes=shift_types,
        forbiddenShiftTypeSuccessions=forbidden,
        contracts=contracts,
        nurses=nurses,
    )


def load_history(path: str) -> History:
    lines = Path(path).read_text().splitlines()
    idx = 0

    def skip_blank():
        nonlocal idx
        while idx < len(lines) and lines[idx].strip() == "":
            idx += 1

    # HISTORY
    skip_blank()
    assert "HISTORY" in lines[idx]
    idx += 1
    parts = lines[idx].strip().split()
    week = int(parts[0])
    scenario = parts[1]
    idx += 1
    skip_blank()

    # NURSE_HISTORY
    assert "NURSE_HISTORY" in lines[idx]
    idx += 1
    nurse_history = []
    while idx < len(lines) and lines[idx].strip():
        parts = lines[idx].strip().split()
        nurse_history.append(
            NurseHistory(
                nurse=parts[0],
                numberOfAssignments=int(parts[1]),
                numberOfWorkingWeekends=int(parts[2]),
                lastAssignedShiftType=parts[3],
                numberOfConsecutiveAssignments=int(parts[4]),
                numberOfConsecutiveWorkingDays=int(parts[5]),
                numberOfConsecutiveDaysOff=int(parts[6]),
            )
        )
        idx += 1

    return History(week=week, scenario=scenario, nurseHistory=nurse_history)


def load_week_data(path: str) -> WeekData:
    lines = Path(path).read_text().splitlines()
    idx = 0

    def skip_blank():
        nonlocal idx
        while idx < len(lines) and lines[idx].strip() == "":
            idx += 1

    # WEEK_DATA
    skip_blank()
    assert "WEEK_DATA" in lines[idx]
    idx += 1
    scenario = lines[idx].strip()
    idx += 1
    skip_blank()

    # REQUIREMENTS
    assert "REQUIREMENTS" in lines[idx]
    idx += 1
    requirements = []
    while (
        idx < len(lines)
        and lines[idx].strip()
        and not lines[idx].strip().startswith("SHIFT_OFF")
    ):
        parts = lines[idx].strip().split()
        shift_type = parts[0]
        skill = parts[1]
        day_reqs = []
        for i in range(7):
            mn, opt = _parse_pair(parts[2 + i])
            day_reqs.append(DayRequirement(minimum=mn, optimal=opt))
        requirements.append(
            CoverRequirement(
                shiftType=shift_type,
                skill=skill,
                requirementOnMonday=day_reqs[0],
                requirementOnTuesday=day_reqs[1],
                requirementOnWednesday=day_reqs[2],
                requirementOnThursday=day_reqs[3],
                requirementOnFriday=day_reqs[4],
                requirementOnSaturday=day_reqs[5],
                requirementOnSunday=day_reqs[6],
            )
        )
        idx += 1
    skip_blank()

    # SHIFT_OFF_REQUESTS
    shift_off_requests = []
    if idx < len(lines) and "SHIFT_OFF_REQUESTS" in lines[idx]:
        idx += 1
        while idx < len(lines) and lines[idx].strip():
            parts = lines[idx].strip().split()
            shift_off_requests.append(
                ShiftOffRequest(
                    nurse=parts[0],
                    shiftType=parts[1],
                    day=parts[2],
                )
            )
            idx += 1

    return WeekData(
        scenario=scenario,
        requirements=requirements,
        shiftOffRequests=shift_off_requests,
    )


def load_solution(sol_dir: str) -> Solution:
    """Load a solution from a directory of per-week Sol-*.txt files + validator.txt."""
    sol_path = Path(sol_dir)
    sol_files = sorted(sol_path.glob("Sol-*.txt"), key=_solution_stage_index)
    weekly_assignments: list[list[Assignment]] = []

    for sol_file in sol_files:
        lines = sol_file.read_text().splitlines()
        assignments = []
        in_assignments = False
        for line in lines:
            line = line.strip()
            if line.startswith("ASSIGNMENTS"):
                in_assignments = True
                continue
            if in_assignments and line:
                parts = line.split()
                if len(parts) >= 4:
                    assignments.append(
                        Assignment(
                            nurse=parts[0],
                            day=parts[1],
                            shiftType=parts[2],
                            skill=parts[3],
                        )
                    )
        weekly_assignments.append(assignments)

    cost = 0
    validator_file = sol_path / "validator.txt"
    if validator_file.exists():
        for line in validator_file.read_text().splitlines():
            if "Total cost:" in line:
                cost = int(line.split(":")[-1].strip())
                break

    return Solution(assignments=weekly_assignments, cost=cost)


def _solution_stage_index(path: Path) -> tuple[int, str]:
    match = re.match(r"Sol-.+-(\d+)\.txt$", path.name)
    if not match:
        return (10**9, path.name)
    return (int(match.group(1)), path.name)


def load_instance(
    scenario_path: str, history_path: str, week_paths: list[str]
) -> Instance:
    """Load a static INRC-II instance from scenario + history + week data files."""
    scenario = load_scenario(scenario_path)
    history = load_history(history_path)
    weeks = [load_week_data(wp) for wp in week_paths]
    return Instance(scenario=scenario, history=history, weeks=weeks)


def enumerate_instances(data_dir: str) -> list[dict]:
    """List all valid (scenario, history, week-sequence, solution) combinations.

    Returns a list of dicts with keys:
        name: e.g. "n005w4_H0_WD1-2-3-3"
        scenario_path: path to Sc-*.txt
        history_path: path to H0-*.txt
        week_paths: list of WD-*.txt paths (in order)
        solution_dir: path to Solution_* directory (if exists)
        num_nurses: number of nurses (from name)
        num_weeks: number of weeks used
    """
    base = Path(data_dir)
    results = []

    for instance_dir in sorted(base.iterdir()):
        if not instance_dir.is_dir():
            continue

        instance_name = instance_dir.name
        scenario_file = instance_dir / f"Sc-{instance_name}.txt"
        if not scenario_file.exists():
            continue

        # Parse nurse count from name
        m = re.match(r"n(\d+)w(\d+)", instance_name)
        if not m:
            continue
        num_nurses = int(m.group(1))

        # Find all history files
        history_files = sorted(instance_dir.glob(f"H0-{instance_name}-*.txt"))

        # Find all week data files
        week_files = sorted(instance_dir.glob(f"WD-{instance_name}-*.txt"))

        # Find solution directories to determine valid combinations
        sol_dirs = sorted(instance_dir.glob("Solution_H_*"))

        for sol_dir in sol_dirs:
            # Parse: Solution_H_{hist_idx}-WD_{w1}-{w2}-...
            dir_name = sol_dir.name
            sol_match = re.match(r"Solution_H_(\d+)-WD_([\d-]+)", dir_name)
            if not sol_match:
                continue

            hist_idx = int(sol_match.group(1))
            week_indices = [int(x) for x in sol_match.group(2).split("-")]

            history_path = instance_dir / f"H0-{instance_name}-{hist_idx}.txt"
            if not history_path.exists():
                continue

            week_paths = []
            valid = True
            for wi in week_indices:
                wp = instance_dir / f"WD-{instance_name}-{wi}.txt"
                if not wp.exists():
                    valid = False
                    break
                week_paths.append(str(wp))

            if not valid:
                continue

            wd_label = "-".join(str(x) for x in week_indices)
            name = f"{instance_name}_H{hist_idx}_WD{wd_label}"

            results.append(
                {
                    "name": name,
                    "scenario_path": str(scenario_file),
                    "history_path": str(history_path),
                    "week_paths": week_paths,
                    "solution_dir": str(sol_dir),
                    "num_nurses": num_nurses,
                    "num_weeks": len(week_indices),
                }
            )

    # Also include combinations without solution directories (history + all weeks)
    # if no solution dirs were found for an instance
    instance_names_with_solutions = {r["name"].split("_H")[0] for r in results}
    for instance_dir in sorted(base.iterdir()):
        if not instance_dir.is_dir():
            continue
        instance_name = instance_dir.name
        if instance_name in instance_names_with_solutions:
            continue

        scenario_file = instance_dir / f"Sc-{instance_name}.txt"
        if not scenario_file.exists():
            continue

        m = re.match(r"n(\d+)w(\d+)", instance_name)
        if not m:
            continue
        num_nurses = int(m.group(1))
        num_weeks_total = int(m.group(2))

        history_files = sorted(instance_dir.glob(f"H0-{instance_name}-*.txt"))
        week_files = sorted(instance_dir.glob(f"WD-{instance_name}-*.txt"))

        for hf in history_files:
            hist_match = re.match(rf"H0-{instance_name}-(\d+)\.txt", hf.name)
            if not hist_match:
                continue
            hist_idx = int(hist_match.group(1))

            # Use first num_weeks_total week files
            if len(week_files) >= num_weeks_total:
                wp_list = [str(wf) for wf in week_files[:num_weeks_total]]
                wd_indices = []
                for wf in week_files[:num_weeks_total]:
                    wm = re.match(rf"WD-{instance_name}-(\d+)\.txt", wf.name)
                    if wm:
                        wd_indices.append(wm.group(1))
                wd_label = "-".join(wd_indices)
                name = f"{instance_name}_H{hist_idx}_WD{wd_label}"

                results.append(
                    {
                        "name": name,
                        "scenario_path": str(scenario_file),
                        "history_path": str(hf),
                        "week_paths": wp_list,
                        "solution_dir": None,
                        "num_nurses": num_nurses,
                        "num_weeks": num_weeks_total,
                    }
                )

    return results
