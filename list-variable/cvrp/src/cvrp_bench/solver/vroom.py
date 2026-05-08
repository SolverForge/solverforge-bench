import vroom

from cvrp_bench.domain.models import Instance, Solution


def solve_with_vroom(instance: Instance, time_limit: int) -> Solution:
    """
    Code for solving the CVRP using vroom. Code heavily inspired by this documentation of the tool:
    https://github.com/VROOM-Project/pyvroom
    """
    problem_instance = vroom.Input()
    problem_instance.set_durations_matrix(
        profile="car", matrix_input=instance.edge_weight.round()
    )
    problem_instance.add_vehicle(
        [
            vroom.Vehicle(id=i, capacity=[instance.capacity], start=0, end=0)
            for i, _ in enumerate(instance.demand)
        ]
    )
    problem_instance.add_job(
        [
            vroom.Job(id=i, location=i, delivery=[instance.demand[i]])
            for i in range(1, len(instance.demand))
        ]
    )
    solution = problem_instance.solve(exploration_level=5, nb_threads=1)

    routes = {}
    for _, row in solution.routes.iterrows():
        vehicle = row["vehicle_id"]
        if vehicle not in routes:
            routes[vehicle] = []
        if row["location_index"] != 0:
            routes[vehicle].append(row["location_index"])
    cost = solution.summary.cost
    return Solution(cost=cost, routes=list(routes.values()))
