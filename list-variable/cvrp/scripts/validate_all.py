import vrplib
from pathlib import Path
from cvrp_bench.domain.models import Instance, Solution
from cvrp_bench.domain.utils import validate


instance_names = {f.name.split(".")[0] for f in Path("data/X").iterdir() if f.is_file()}

for name in instance_names:
    instance = vrplib.read_instance(f"data/X/{name}.vrp")
    solution = vrplib.read_solution(f"data/X/{name}.sol")
    instance = Instance.model_validate(instance)
    solution = Solution.model_validate(solution)
    validate(solution, instance)
