"""Validate the bundled CVRP instances, their shipped solutions, and their
official references.

The instance set is derived from the ``.vrp`` files rather than from every file
in the directory: the directory also holds the pinned reference catalog and the
official CVRPLIB table, neither of which is an instance.
"""

from pathlib import Path

import vrplib

from cvrp_bench.domain.models import Instance, Solution
from cvrp_bench.domain.utils import validate
from solverforge_bench.references import catalog_instances, reference_for

DATA_DIR = Path("data/X")

instance_names = sorted(p.stem for p in DATA_DIR.glob("*.vrp"))

catalogs = catalog_instances(DATA_DIR)
assert catalogs == set(instance_names), (
    "the reference catalog and the bundled instances disagree: "
    f"missing references {sorted(set(instance_names) - catalogs)}, "
    f"extra references {sorted(catalogs - set(instance_names))}"
)

for name in instance_names:
    instance = Instance.model_validate(vrplib.read_instance(f"data/X/{name}.vrp"))
    solution = Solution.model_validate(vrplib.read_solution(f"data/X/{name}.sol"))
    validate(solution, instance)
    reference = reference_for(DATA_DIR, name)
    assert reference.reference_cost > 0
    assert reference.status in {"closed", "open"}

print(
    f"validated {len(instance_names)} instances, their shipped solutions, "
    f"and {len(catalogs)} official references"
)
