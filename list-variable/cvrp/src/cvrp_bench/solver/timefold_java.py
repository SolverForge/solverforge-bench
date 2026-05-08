import json
import subprocess
from pathlib import Path

from cvrp_bench.domain.models import Instance, Solution

# Fat JAR produced by: mvn -f <this_dir>/timefold_java/pom.xml package
_JAR_PATH = Path(__file__).parent / "timefold_java" / "target" / "timefold-cvrp.jar"


def solve_with_timefold_java(instance: Instance, time_limit: int) -> Solution:
    """
    Solve the CVRP using Timefold Solver running on the JVM (Java).

    The Java solver uses this constraint model:
      - Hard: vehicle capacity (penalise overload by excess demand)
      - Soft: minimise total distance (depot->first, visit->visit, last->depot arcs)
    Distance values are pre-rounded to match round(instance.edge_weight[i][j]).

    The Java process is invoked via subprocess; the instance is passed as JSON on
    stdin and the solution is returned as JSON on stdout.

    Build the JAR once before use:
        mvn -f src/cvrp_bench/solver/timefold_java/pom.xml package -q
    """
    # 1 transform: build input JSON matching CvrpInput in Main.java
    instance_json = json.dumps(
        {
            "dimension": instance.dimension,
            "capacity": instance.capacity,
            "demand": instance.demand.tolist(),
            "depot": int(instance.depot[0]),
            "distance_matrix": instance.edge_weight.round().astype(int).tolist(),
        }
    )

    # 2 solve: call the fat JAR, passing time_limit as CLI arg and instance as stdin
    result = subprocess.run(
        ["java", "-jar", str(_JAR_PATH), str(time_limit)],
        input=instance_json.encode(),
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"timefold_java solver failed (exit {result.returncode}):\n"
            f"{result.stderr.decode()}"
        )

    # 3 transform: routes are already depot-excluded lists of customer indices
    output = json.loads(result.stdout)
    return Solution(routes=output["routes"], cost=output["cost"])
