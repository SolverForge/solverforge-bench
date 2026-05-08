from cvrp_bench.domain.models import Instance, Solution
import hygese as hgs


def solve_with_pyhygese(instance: Instance, time_limit: int) -> Solution:
    # Simple pyhygese baseline would go here

    data = dict()
    data["distance_matrix"] = instance.edge_weight.round()
    data["num_vehicles"] = len(instance.demand) - 1
    data["depot"] = instance.depot[0]
    data["demands"] = instance.demand
    data["vehicle_capacity"] = instance.capacity
    data["service_times"] = [0 for _ in instance.demand]

    # Solver initialization
    ap = hgs.AlgorithmParameters(timeLimit=time_limit)  # seconds
    hgs_solver = hgs.Solver(parameters=ap, verbose=True)

    # Solve
    result = hgs_solver.solve_cvrp(data)
    return Solution(routes=result.routes, cost=result.cost)
