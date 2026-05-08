from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

from cvrp_bench.domain.models import Instance, Solution


def solve_with_ortools(instance: Instance, time_limit: int) -> Solution:
    """
    Code for solving the CVRP using google or tools. Code heavily inspired by this documentation of the tool:
    https://developers.google.com/optimization/routing/cvrp
    """

    # create routing index manager
    manager = pywrapcp.RoutingIndexManager(
        len(instance.edge_weight), len(instance.demand), 0
    )
    # create routing model
    routing = pywrapcp.RoutingModel(manager)

    # Create and register a transit callback.
    def distance_callback(from_index, to_index):
        """Returns the distance between the two nodes."""
        # Convert from routing variable Index to distance matrix NodeIndex.
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return round(instance.edge_weight[from_node][to_node])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    # Define cost of each arc.
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Add Capacity constraint.
    def demand_callback(from_index):
        """Returns the demand of the node."""
        # Convert from routing variable Index to demands NodeIndex.
        from_node = manager.IndexToNode(from_index)
        return instance.demand[from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        [instance.capacity for _ in instance.demand],  # vehicle maximum capacities
        True,  # start cumul to zero
        "Capacity",
    )

    # Setting first solution heuristic.
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(time_limit)

    # Solve the problem.
    solution = routing.SolveWithParameters(search_parameters)
    if solution is None:
        return None
    routes = []
    for vehicle_id in range(len(instance.demand)):
        if not routing.IsVehicleUsed(solution, vehicle_id):
            continue
        route = []
        index = routing.Start(vehicle_id)
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            if node_index != 0:
                route.append(node_index)
            index = solution.Value(routing.NextVar(index))
        routes.append(route)
    return Solution(cost=solution.ObjectiveValue(), routes=routes)
