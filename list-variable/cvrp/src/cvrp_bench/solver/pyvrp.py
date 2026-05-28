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
    m.add_depot(x=depot_coords[0], y=depot_coords[1])
    _ = [
        m.add_client(float(coord[0]), float(coord[1]), delivery=int(demand))
        for coord, demand in list(zip(instance.node_coord, instance.demand))[1:]
    ]
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
    # 3 transform pyvrp output to solution object
    return solver_result(
        Solution(routes=[list(route) for route in res.best.routes()], cost=res.cost()),
        witness,
    )
