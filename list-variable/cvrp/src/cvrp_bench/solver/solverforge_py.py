from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from solverforge import (
    CapacityRouteFeasibility,
    ConstraintFactory,
    HardSoftScore,
    ListRouteHooks,
    ListSavingsHooks,
    RowField,
    Solver,
    constraint_provider,
    planning_entity,
    planning_list_variable,
    planning_solution,
)

from cvrp_bench.domain.models import Instance, Solution
from cvrp_bench.domain.utils import calculate_cost
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import SolverResult
from solverforge_bench.solverforge_config import solver_config_for_time_limit


_SOLVER_CONFIG_PATH = Path(__file__).with_name("solverforge_py.toml")


def _route_load(route: Any) -> int:
    return sum(int(route.demands[visit]) for visit in route.visits)


def _route_overload(route: Any) -> int:
    return max(0, _route_load(route) - int(route.capacity))


def _route_cost(route: Any) -> int:
    if not route.visits:
        return 0
    total = 0
    previous = int(route.depot)
    for visit in route.visits:
        total += int(route.distance_matrix[previous][visit])
        previous = int(visit)
    return total + int(route.distance_matrix[previous][int(route.depot)])


@planning_entity
class Route:
    visits = planning_list_variable(
        element_collection="customer_values",
        route=ListRouteHooks(
            depot=RowField("depot"),
            distance=RowField("distance_matrix"),
            feasible=CapacityRouteFeasibility(
                capacity=RowField("capacity"),
                demand=RowField("demands"),
            ),
        ),
        savings=ListSavingsHooks(
            depot=RowField("depot"),
            metric_class=RowField("metric_class"),
            distance=RowField("distance_matrix"),
            feasible=CapacityRouteFeasibility(
                capacity=RowField("capacity"),
                demand=RowField("demands"),
            ),
        ),
        cross_position_distance=RowField("distance_matrix"),
        intra_position_distance=RowField("distance_matrix"),
    )

    def __init__(
        self,
        *,
        route_id: int,
        depot: int,
        capacity: int,
        demands: list[int],
        distance_matrix: list[list[int]],
    ) -> None:
        self.route_id = route_id
        self.depot = depot
        self.metric_class = 0
        self.capacity = capacity
        self.demands = demands
        self.distance_matrix = distance_matrix
        self.visits: list[int] = []


@constraint_provider
def _cvrp_constraints(factory: ConstraintFactory) -> list[object]:
    return [
        factory.for_each_unassigned_element(Route, "visits")
        .penalize(HardSoftScore.of_hard(1))
        .named("all customers assigned"),
        factory.for_each(Route)
        .filter(lambda route: _route_overload(route) > 0)
        .penalize(lambda route: HardSoftScore.of_hard(_route_overload(route)))
        .named("vehicle capacity"),
        factory.for_each(Route)
        .penalize(lambda route: HardSoftScore.of_soft(_route_cost(route)))
        .named("total distance"),
    ]


@planning_solution(score=HardSoftScore, constraints=_cvrp_constraints)
class CvrpPythonPlan:
    routes: list[Route]

    def __init__(self, instance: Instance) -> None:
        depot = int(instance.depot[0])
        customer_values = [
            node_idx for node_idx in range(int(instance.dimension)) if node_idx != depot
        ]
        demands = [int(value) for value in instance.demand.tolist()]
        distance_matrix = instance.edge_weight.round().astype(int).tolist()
        self.depot = depot
        self.demands = demands
        self.distance_matrix = distance_matrix
        self.customer_values = customer_values
        self.routes = [
            Route(
                route_id=route_id,
                depot=depot,
                capacity=int(instance.capacity),
                demands=demands,
                distance_matrix=distance_matrix,
            )
            for route_id in range(len(customer_values))
        ]
        self.score = None


def solve_with_solverforge_py(instance: Instance, time_limit: int) -> SolverResult:
    instance_payload = json.dumps(
        {
            "dimension": instance.dimension,
            "capacity": instance.capacity,
            "demand": instance.demand.tolist(),
            "depot": int(instance.depot[0]),
            "distance_matrix": instance.edge_weight.round().astype(int).tolist(),
        },
        sort_keys=True,
    )
    witness = make_fair_start_witness(
        benchmark_name="cvrp",
        solver="solverforge-py",
        planning_state="empty_list_variables",
        solver_input=instance_payload,
    )
    plan = CvrpPythonPlan(instance)
    config = _solver_config(time_limit)

    emit_fair_start_witness(witness)
    solved = Solver.solve(plan, config)

    routes = [list(route.visits) for route in solved.routes if route.visits]
    solution = Solution(
        routes=routes, cost=calculate_cost(Solution(routes=routes, cost=0), instance)
    )
    return solver_result(solution, witness)


def _solver_config(time_limit: int) -> dict[str, Any]:
    return solver_config_for_time_limit(_SOLVER_CONFIG_PATH, time_limit)
