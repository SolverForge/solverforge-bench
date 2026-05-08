from cvrp_bench.domain.models import Instance, Solution

import vrp_cli
from cvrp_bench.solver.rustvrp import pragmatic_types as prg
from cvrp_bench.solver.rustvrp import config_types as cfg
import json
from pydantic import TypeAdapter


def solve_with_rustvrp(instance: Instance, time_limit: int) -> Solution:
    """
    Code for solving the CVRP using rustvrp. Code heavily inspired by this documentation of the tool:
    https://github.com/reinterpretcat/vrp/tree/master/examples/python-interop
    """
    # if you want to use approximation, you can skip this definition and pass empty list later
    # also there is a get_locations method to get list of locations in expected order.
    # you can use this list to fetch routing matrix externally
    matrix = prg.RoutingMatrix(
        profile="normal_car",
        durations=list(instance.edge_weight.flatten().round()),
        distances=list(instance.edge_weight.flatten().round()),
    )

    # specify termination criteria: max running time in seconds or max amount of refinement generations
    config = cfg.Config(termination=cfg.Termination(maxTime=time_limit))

    # specify test problem
    problem = prg.Problem(
        plan=prg.Plan(
            jobs=[
                prg.Job(
                    id=str(i),
                    deliveries=[
                        prg.JobTask(
                            places=[
                                prg.JobPlace(
                                    location=prg.Location(index=i),
                                    duration=0,
                                ),
                            ],
                            demand=[demand],
                        )
                    ],
                )
                for i, demand in enumerate(instance.demand)
            ]
        ),
        fleet=prg.Fleet(
            vehicles=[
                prg.VehicleType(
                    typeId="vehicle",
                    vehicleIds=[f"vehicle_{i}" for i, _ in enumerate(instance.demand)],
                    profile=prg.VehicleProfile(matrix="normal_car"),
                    costs=prg.VehicleCosts(fixed=0, distance=1, time=0),
                    shifts=[
                        prg.VehicleShift(
                            start=prg.VehicleShiftStart(
                                earliest="2000-01-01T00:00:00Z",
                                location=prg.Location(index=0),
                            ),
                            end=prg.VehicleShiftEnd(
                                latest="2100-01-01T00:00:00Z",
                                location=prg.Location(index=0),
                            ),
                        )
                    ],
                    capacity=[instance.capacity],
                )
            ],
            profiles=[prg.RoutingProfile(name="normal_car")],
        ),
    )

    # run solver and deserialize result into solution model
    solution = prg.Solution(
        **json.loads(
            vrp_cli.solve_pragmatic(
                problem=TypeAdapter(prg.Problem).dump_json(problem).decode(),
                matrices=[TypeAdapter(prg.RoutingMatrix).dump_json(matrix).decode()],
                config=TypeAdapter(cfg.Config).dump_json(config).decode(),
            )
        )
    )
    cost = solution.statistic.cost
    routes = []
    for tour in solution.tours:
        route = []
        for stop in tour.stops:
            idx = stop.location.index
            if idx != 0:
                route.append(idx)
        routes.append(route)
    return Solution(routes=routes, cost=cost)
