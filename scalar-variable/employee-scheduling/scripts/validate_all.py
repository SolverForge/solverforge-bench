from pathlib import Path

from employee_scheduling_bench.loader import (
    enumerate_instances,
    load_instance,
    load_solution,
)
from employee_scheduling_bench.validation import validate


def main() -> None:
    data_dir = Path("data/inrc2")
    checked = 0

    for inst_info in enumerate_instances(str(data_dir)):
        if not inst_info["solution_dir"]:
            continue

        instance = load_instance(
            inst_info["scenario_path"],
            inst_info["history_path"],
            inst_info["week_paths"],
        )
        solution = load_solution(inst_info["solution_dir"])
        cost = validate(solution, instance)

        if solution.cost is not None and solution.cost > 0 and cost != solution.cost:
            raise AssertionError(
                f"{inst_info['name']}: validator cost mismatch, local={cost}, reference={solution.cost}"
            )

        checked += 1

    print(f"Validated {checked} INRC-II reference solution directories.")


if __name__ == "__main__":
    main()
