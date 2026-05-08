from cvrp_bench.domain.models import Instance, Solution


class OverloadError(Exception):
    pass


class OrderMissingError(Exception):
    pass


class WrongCostError(Exception):
    pass


def validate(solution: Solution, instance: Instance) -> bool:
    """
    Validates whether all tours of a solution are feasible regarding capacity constraint and whether the costs are correct

    :param solution: Description
    :type solution: Solution
    :param instance: Description
    :type instance: Instance
    :return: Description
    :rtype: bool
    """

    for i, route in enumerate(solution.routes):
        load = get_load(route, instance)

        if load > instance.capacity:
            raise OverloadError(
                f"Tour {i} for instance {instance.name} not feasible: {load}/{instance.capacity} load."
            )
    total_cost = calculate_cost(solution=solution, instance=instance)
    if total_cost != solution.cost:
        raise WrongCostError(
            f"Scores for instance {instance.name} do not match: Calculated vs in-data: {total_cost} vs {solution.cost}"
        )
    orders = set(i for i in range(1, len(instance.demand)))
    for route in solution.routes:
        for stop in route:
            orders.remove(stop)
    if len(orders) > 0:
        raise OrderMissingError(
            f"For instance {instance.name}, the following orders were not served: {orders}"
        )
    print(f"Instance and solution file for instance {instance.name} match.")
    return True


def calculate_cost(solution: Solution, instance: Instance) -> int:
    return sum(get_distance(route, instance=instance) for route in solution.routes)


def get_distance(route: list, instance: Instance) -> float:
    depot = instance.depot[0]
    total_distance = 0
    current_stop = depot
    for stop in route:
        total_distance += round(instance.edge_weight[current_stop, stop])
        current_stop = stop
    return total_distance + round(instance.edge_weight[current_stop, depot])


def get_load(route: list, instance: Instance) -> int:
    return sum(instance.demand[stop] for stop in route)
