import argparse
import time
from pathlib import Path
from datetime import datetime

import polars as pl

from employee_scheduling_bench.loader import (
    dataset_group_names,
    load_instance,
    load_solution,
    enumerate_instances,
)
from employee_scheduling_bench.solver.solver import create_solver
from employee_scheduling_bench.domain.validation import validate

DEFAULT_SOLVER_NAMES = ["solverforge", "timefold_java", "ortools"]
DEFAULT_TIME_LIMITS = [1, 10, 60]


parser = argparse.ArgumentParser()
parser.add_argument(
    "--solver",
    nargs="+",
    choices=DEFAULT_SOLVER_NAMES,
    default=DEFAULT_SOLVER_NAMES,
)
parser.add_argument(
    "--dataset-set",
    default=None,
    help="Dataset group from data/inrc2/manifest.json, e.g. canonical, late, test_with_solutions, quick",
)
parser.add_argument(
    "--datasets",
    nargs="+",
    default=None,
    help="Filter by instance group name, e.g. n005w4 n030w4",
)
parser.add_argument("--time-limits", nargs="+", type=int, default=DEFAULT_TIME_LIMITS)
args = parser.parse_args()

data_dir = Path("data/inrc2")
instances = enumerate_instances(str(data_dir))
dataset_set_label = args.dataset_set or ("custom" if args.datasets else "all")

if args.dataset_set:
    dataset_names = dataset_group_names(str(data_dir), args.dataset_set)
    instances = [
        inst
        for inst in instances
        if inst["name"].split("_H", maxsplit=1)[0] in dataset_names
    ]

if args.datasets:
    instances = [
        inst
        for inst in instances
        if any(inst["name"].startswith(ds) for ds in args.datasets)
    ]

solver_names = args.solver
time_limits = args.time_limits

results = {
    "Instance": [],
    "Dataset Set": [],
    "Nurses": [],
    "Weeks": [],
    "Time Limit (s)": [],
    "Actual Time (s)": [],
    "Solver": [],
    "Hard Feasible": [],
    "Cost": [],
    "Reference Cost": [],
    "Quality Ratio": [],
    "Validation Error": [],
}

for inst_info in instances:
    instance = load_instance(
        inst_info["scenario_path"],
        inst_info["history_path"],
        inst_info["week_paths"],
    )

    best_solution = None
    if inst_info["solution_dir"]:
        best_solution = load_solution(inst_info["solution_dir"])

    for time_limit in time_limits:
        solvers = {
            name: create_solver(method=name, time_limit=time_limit)
            for name in solver_names
        }
        for s_name, solver in solvers.items():
            tic = time.time()
            solution = None
            solver_error = None
            try:
                solution = solver(instance, time_limit)
            except Exception as exc:
                solver_error = exc
            toc = time.time()
            real_time = toc - tic

            results["Instance"].append(inst_info["name"])
            results["Dataset Set"].append(dataset_set_label)
            results["Nurses"].append(inst_info["num_nurses"])
            results["Weeks"].append(inst_info["num_weeks"])
            results["Time Limit (s)"].append(time_limit)
            results["Actual Time (s)"].append(float(real_time))
            results["Solver"].append(s_name)
            results["Reference Cost"].append(
                best_solution.cost if best_solution else None
            )

            if solver_error is not None:
                results["Hard Feasible"].append(False)
                results["Cost"].append(None)
                results["Quality Ratio"].append(None)
                results["Validation Error"].append(
                    f"{solver_error.__class__.__name__}: {solver_error}"
                )
                continue

            try:
                assert solution is not None
                cost = validate(solution=solution, instance=instance)
                results["Hard Feasible"].append(True)
                results["Cost"].append(cost)
                if best_solution and best_solution.cost > 0:
                    results["Quality Ratio"].append(float(cost / best_solution.cost))
                else:
                    results["Quality Ratio"].append(None)
                results["Validation Error"].append("")
            except Exception as exc:
                results["Hard Feasible"].append(False)
                results["Cost"].append(None)
                results["Quality Ratio"].append(None)
                results["Validation Error"].append(f"{exc.__class__.__name__}: {exc}")

df = pl.DataFrame(results)
df.write_csv(f"data/benchmark_employee_scheduling_{datetime.now():%Y%m%d_%H%M%S}.csv")
