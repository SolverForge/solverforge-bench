import numpy as np
import pyvrp

from delivery_scale_bench.domain.models import SPEED_MPS, Instance
from delivery_scale_bench.solver.instance_json import serialize_instance
from delivery_scale_bench.solver.output import solution_from_native
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import SolverResult

BENCHMARK_NAME = "delivery-scale"
_MATRIX_BLOCK_ROWS = 512


def solve_with_pyvrp(instance: Instance, time_limit: int) -> SolverResult:
    """Solve with PyVRP's hybrid genetic search on the delivery ruleset.

    Location 0 is the depot and location ``i + 1`` is delivery ``i``. Distance
    and duration are both the validator's travel seconds, so PyVRP's distance
    objective is the benchmark's total travel time. A client's ``tw_late`` is
    its latest service start, ``max_end - service``.
    """

    instance_json = serialize_instance(instance)
    witness = make_fair_start_witness(
        benchmark_name=BENCHMARK_NAME,
        solver="pyvrp",
        planning_state="external_solver_model",
        solver_input=instance_json,
    )
    deliveries = instance.deliveries
    xs = np.array([instance.depot_x, *(d.x for d in deliveries)], dtype=np.int64)
    ys = np.array([instance.depot_y, *(d.y for d in deliveries)], dtype=np.int64)
    travel = _travel_matrix(xs, ys)
    data = pyvrp.ProblemData(
        locations=[pyvrp.Location(float(x), float(y)) for x, y in zip(xs, ys)],
        clients=[
            pyvrp.Client(
                location=index + 1,
                delivery=[delivery.demand],
                service_duration=delivery.service,
                tw_early=delivery.min_start,
                tw_late=delivery.max_end - delivery.service,
            )
            for index, delivery in enumerate(deliveries)
        ],
        depots=[pyvrp.Depot(location=0)],
        vehicle_types=[
            pyvrp.VehicleType(
                num_available=instance.vehicle_count,
                capacity=[instance.capacity],
                tw_early=instance.departure_time,
                start_late=instance.departure_time,
            )
        ],
        distance_matrices=[travel],
        duration_matrices=[travel],
    )
    del travel

    emit_fair_start_witness(witness)
    result = pyvrp.solve(data, stop=pyvrp.stop.MaxRuntime(time_limit), display=True)
    best = result.best
    # A route iterates activities (depot start/end plus one per client); the
    # client activity's idx is the 0-based client index, i.e. the delivery index.
    routes = [
        [activity.idx for activity in route if activity.is_client()]
        for route in best.routes()
    ]
    output = {
        "routes": routes,
        "reported_cost": int(result.cost()) if best.is_feasible() else None,
        "fresh_cost": int(best.distance()),
        "feasible": best.is_feasible(),
        "time_warp": int(best.time_warp()),
        "excess_load": [int(value) for value in best.excess_load()],
        "iterations": result.num_iterations,
    }
    solver_metadata = {key: value for key, value in output.items() if key != "routes"}
    return solver_result(
        solution_from_native(
            instance,
            output,
            solver_label="PyVRP",
            solver_metadata=solver_metadata,
        ),
        witness,
    )


def _travel_matrix(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """The validator's travel rule, row block by row block to bound memory."""

    size = len(xs)
    matrix = np.empty((size, size), dtype=np.int64)
    for start in range(0, size, _MATRIX_BLOCK_ROWS):
        stop = min(start + _MATRIX_BLOCK_ROWS, size)
        dx = xs[start:stop, None] - xs[None, :]
        dy = ys[start:stop, None] - ys[None, :]
        metres = np.sqrt((dx * dx + dy * dy).astype(np.float64))
        matrix[start:stop] = np.floor(metres / SPEED_MPS + 0.5).astype(np.int64)
    return matrix
