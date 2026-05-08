import argparse
import time
import vrplib
from pathlib import Path
from cvrp_bench.domain.models import Instance, Solution
import polars as pl

from cvrp_bench.solver.solver import AVAILABLE_METHODS, create_solver
from cvrp_bench.domain.utils import validate
from datetime import datetime

DEFAULT_SOLVER_NAMES = [
    "timefold_java",
    "pyvrp",
    "solverforge",
]
DEFAULT_TIME_LIMITS = [1, 10, 60]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the CVRP benchmark suite.")
    parser.add_argument(
        "--solver",
        action="append",
        choices=AVAILABLE_METHODS,
        dest="solver_names",
        help="Solver to run. Repeat to include multiple solvers.",
    )
    parser.add_argument(
        "--time-limits",
        nargs="+",
        type=int,
        default=DEFAULT_TIME_LIMITS,
        help="Time limits in seconds.",
    )
    parser.add_argument(
        "--num-instances",
        type=int,
        default=None,
        help="Limit the number of instances for a smoke run.",
    )
    return parser.parse_args()


args = parse_args()
instance_names = list(
    set(f.name.split(".")[0] for f in Path("data/X").iterdir() if f.is_file())
)
solver_names = args.solver_names or DEFAULT_SOLVER_NAMES
time_limits = args.time_limits
num_instances = args.num_instances

results = {
    "Instance": [],
    "Size": [],
    "Time Limit (s)": [],
    "Actual Time (s)": [],
    "Solver": [],
    "Solution Quality": [],
}
instance_names.sort()
for name in instance_names[:num_instances] if num_instances else instance_names:
    instance = vrplib.read_instance(f"data/X/{name}.vrp")
    solution = vrplib.read_solution(f"data/X/{name}.sol")
    instance = Instance.model_validate(instance)
    best_solution = Solution.model_validate(solution)
    for time_limit in time_limits:
        if time_limit is None:
            assert solver_names[0] == "vroom"
            time_limit = 1
        solvers = {
            name: create_solver(method=name, time_limit=time_limit)
            for name in solver_names
        }
        for s_name, solver in solvers.items():
            tic = time.time()
            solution = solver(instance, time_limit)
            toc = time.time()
            real_time = toc - tic
            if real_time > time_limit * 1.1:
                print(
                    f"Warning, solver {s_name} took {real_time:2f} s on instance {name} despite setting a time limit of {time_limit} s."
                )

            results["Instance"].append(instance.name)
            results["Size"].append(len(instance.demand))
            results["Time Limit (s)"].append(time_limit)
            results["Actual Time (s)"].append(float(real_time))
            results["Solver"].append(s_name)
            try:
                validate(solution=solution, instance=instance)
                results["Solution Quality"].append(
                    float(solution.cost / best_solution.cost)
                )
            except Exception:  # noqa: E722
                results["Solution Quality"].append(-1.0)
            if s_name == "vroom":
                time_limit = max(
                    1, round(real_time)
                )  # everybody is taking the time that vroom needed

    # just to be save, save after every instance:
    df = pl.DataFrame(results)
    df.write_csv(f"data/benchmark_no_vroom{datetime.now()}.csv")
df = pl.DataFrame(results)
df.write_csv(f"data/benchmark_no_vroom{datetime.now()}.csv")
