from cvrp_bench.domain.models import Instance, Solution
import pyvrp
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import SolverResult


def solve_with_pyvrp(instance: Instance, time_limit: int) -> SolverResult:
    """
    Code for solving the CVRP using pyvrp. Code heavily inspired by this documentation of the tool:
    https://pyvrp.org/examples/quick_tutorial.html

    """
    # 1 transform instance object for pyvrp inputs
    m = pyvrp.Model()
    m.add_vehicle_type(num_available=len(instance.demand), capacity=instance.capacity)
    depot_coords = instance.node_coord[instance.depot[0]]
    # Locations are registered on the model first and referenced by depot or
    # client; the depot is added before any client so location index 0 stays the
    # depot and the edge_weight matrix keeps its original row and column order.
    m.add_depot(m.add_location(float(depot_coords[0]), float(depot_coords[1])))
    for coord, demand in list(zip(instance.node_coord, instance.demand))[1:]:
        m.add_client(
            m.add_location(float(coord[0]), float(coord[1])),
            delivery=int(demand),
        )
    for i, frm in enumerate(m.locations):
        for j, to in enumerate(m.locations):
            m.add_edge(frm, to, round(instance.edge_weight[i][j]))

    # 2 solve by pyvrp
    witness = make_fair_start_witness(
        benchmark_name="cvrp",
        solver="pyvrp",
        planning_state="external_solver_model",
        solver_input=instance,
    )
    emit_fair_start_witness(witness)
    res = m.solve(stop=pyvrp.stop.MaxRuntime(time_limit), display=True)  # one second
    # 3 transform pyvrp output to solution object. A route iterates Activities
    # (depot start/end plus one per client), while the benchmark's Solution model
    # expects node indices. Filter depots out, then shift pyvrp's 0-based client
    # index to the node index: client 0 is node 1, which is how the shipped
    # reference tours and every other CVRP adapter index edge_weight and demand.
    return solver_result(
        Solution(
            routes=[
                [activity.idx + 1 for activity in route if activity.is_client()]
                for route in res.best.routes()
            ],
            cost=res.cost(),
        ),
        witness,
    )
