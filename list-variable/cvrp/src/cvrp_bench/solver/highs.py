import highspy
import numpy as np

from cvrp_bench.domain.models import Instance, Solution
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import (
    NoSolutionFoundError,
    SolverExecutionError,
    SolverResult,
)


def _status_name(h: highspy.Highs) -> str:
    return str(h.modelStatusToString(h.getModelStatus()))


def _build_milp(
    instance: Instance,
) -> tuple[highspy.Highs, dict[tuple[int, int], int], list[int]]:
    """
    Two-index CVRP MILP over the raw edge_weight matrix with single-commodity
    (Gavish-Graves) flow variables: one binary per arc, customer degree 1 over
    all nodes, and a continuous load flow that leaves the depot carrying all
    demand and drops q_j at every customer. Any customer-only cycle would have
    to consume demand around a closed loop, so integer-feasible solutions are
    exactly valid depot routes with per-route load <= capacity; no separated
    cuts are needed for correctness. Capacity is enforced by f_ij <= Q * x_ij:
    a route's first leg carries the whole route demand. No hints, no seeds, no
    warm start: the planning state is an empty arc set.
    """
    demand = [int(value) for value in instance.demand.tolist()]
    capacity = int(instance.capacity)
    num_nodes = len(demand)
    customers = range(1, num_nodes)

    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("log_to_console", False)

    arc_col: dict[tuple[int, int], int] = {}
    costs: list[float] = []
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i == j:
                continue
            arc_col[(i, j)] = len(costs)
            # The benchmark's cost convention is the per-edge-rounded integer
            # matrix (see domain.utils.get_distance and every other adapter).
            costs.append(float(round(instance.edge_weight[i][j])))
    num_arcs = len(costs)

    # Capacity flow columns, one per arc, indexed like arc_col by iteration
    # order; they ride the same arc loop via position = arc index.
    col_lower = np.zeros(num_arcs, dtype=np.float64)
    col_upper = np.full(num_arcs, float(capacity), dtype=np.float64)

    h.addCols(
        num_arcs,
        np.array(costs, dtype=np.float64),
        np.zeros(num_arcs, dtype=np.float64),
        np.ones(num_arcs, dtype=np.float64),
        0,
        np.array([], dtype=np.int32),
        np.array([], dtype=np.int32),
        np.array([], dtype=np.float64),
    )
    h.changeColsIntegrality(
        num_arcs,
        np.arange(num_arcs, dtype=np.int32),
        np.full(num_arcs, highspy.HighsVarType.kInteger, dtype=np.uint8),
    )
    flow_base = num_arcs
    h.addCols(
        num_arcs,
        np.zeros(num_arcs, dtype=np.float64),
        col_lower,
        col_upper,
        0,
        np.array([], dtype=np.int32),
        np.array([], dtype=np.int32),
        np.array([], dtype=np.float64),
    )

    rows_lower: list[float] = []
    rows_upper: list[float] = []
    row_starts: list[int] = []
    row_indices: list[int] = []
    row_values: list[float] = []

    def add_row(entries: list[tuple[int, float]], lower: float, upper: float) -> None:
        row_starts.append(len(row_indices))
        rows_lower.append(lower)
        rows_upper.append(upper)
        for col, coef in entries:
            row_indices.append(col)
            row_values.append(coef)

    # Customer degree: exactly one predecessor and one successor over all
    # nodes (depot included); self-arcs do not exist in the model.
    for j in customers:
        add_row([(arc_col[(i, j)], 1.0) for i in range(num_nodes) if i != j], 1.0, 1.0)
        add_row([(arc_col[(j, i)], 1.0) for i in range(num_nodes) if i != j], 1.0, 1.0)

    # Flow capacity link: f_ij - Q * x_ij <= 0.
    for (i, j), col in arc_col.items():
        add_row(
            [(flow_base + col, 1.0), (col, -float(capacity))],
            -highspy.kHighsInf,
            0.0,
        )

    # All demand leaves the depot once: sum_j f_{0j} = sum_j q_j.
    depot_out = [(flow_base + arc_col[(0, j)], 1.0) for j in customers]
    total_demand = float(sum(demand[1:]))
    add_row(depot_out, total_demand, total_demand)

    # Customer conservation: sum_i f_{ij} - sum_k f_{jk} = q_j.
    for j in customers:
        inflow = [
            (flow_base + arc_col[(i, j)], 1.0) for i in range(num_nodes) if i != j
        ]
        outflow = [
            (flow_base + arc_col[(j, k)], -1.0) for k in range(num_nodes) if k != j
        ]
        add_row(inflow + outflow, float(demand[j]), float(demand[j]))

    h.addRows(
        len(rows_lower),
        np.array(rows_lower, dtype=np.float64),
        np.array(rows_upper, dtype=np.float64),
        len(row_indices),
        np.array(row_starts, dtype=np.int32),
        np.array(row_indices, dtype=np.int32),
        np.array(row_values, dtype=np.float64),
    )
    return h, arc_col, demand


def _extract_routes(
    values,
    arc_col: dict[tuple[int, int], int],
    num_nodes: int,
) -> list[list[int]]:
    successor: dict[int, int] = {}
    for (i, j), col in arc_col.items():
        if values[col] > 0.5:
            if i != 0 and i in successor:
                raise SolverExecutionError(
                    "HiGHS CVRP solution has an ambiguous customer successor"
                )
            successor[i] = j

    routes: list[list[int]] = []
    visited: set[int] = set()
    for first in range(1, num_nodes):
        if values[arc_col[(0, first)]] <= 0.5:
            continue
        route: list[int] = []
        node = first
        while node != 0:
            if node in visited or node not in successor:
                raise SolverExecutionError(
                    "HiGHS CVRP solution contains a customer-only cycle"
                )
            visited.add(node)
            route.append(node)
            node = successor[node]
        routes.append(route)
    if len(visited) != num_nodes - 1:
        raise SolverExecutionError("HiGHS CVRP solution does not serve every customer")
    return routes


def solve_with_highs(instance: Instance, time_limit: int) -> SolverResult:
    """
    HiGHS (highspy) CVRP adapter: the mainline C++ HiGHS core through its
    published Python wheel, solving the same edge_weight routing model as the
    other CVRP adapters from an empty arc set. The flow formulation makes
    subtours structurally impossible, so one MIP solve yields valid routes or
    an honest no-incumbent outcome.
    """
    witness = make_fair_start_witness(
        benchmark_name="cvrp",
        solver="highs",
        planning_state="external_solver_model",
        solver_input=instance,
    )
    emit_fair_start_witness(witness)

    h, arc_col, demand = _build_milp(instance)
    h.setOptionValue("threads", 1)
    h.setOptionValue("random_seed", 1)
    h.setOptionValue("time_limit", float(max(0.1, time_limit)))

    h.run()
    model_status = h.getModelStatus()
    solution = h.getSolution()
    native_fields = {"native_solver_status": _status_name(h)}
    if model_status == highspy.HighsModelStatus.kInfeasible:
        raise NoSolutionFoundError(
            "HiGHS proved the CVRP model infeasible",
            termination_status="proved_infeasible",
            native_fields=native_fields,
        )
    if model_status != highspy.HighsModelStatus.kOptimal and not solution.value_valid:
        raise NoSolutionFoundError(
            "HiGHS returned no CVRP incumbent before the time limit",
            termination_status="no_incumbent",
            native_fields=native_fields,
        )

    routes = _extract_routes(solution.col_value, arc_col, len(demand))
    edge_weight = instance.edge_weight
    cost = 0
    for route in routes:
        previous = 0
        for node in route:
            cost += int(round(float(edge_weight[previous][node])))
            previous = node
        cost += int(round(float(edge_weight[previous][0])))

    objective = int(round(h.getObjectiveValue()))
    if cost != objective:
        raise SolverExecutionError(
            f"HiGHS CVRP reported objective {objective} does not match the "
            f"recomputed route cost {cost}",
            native_fields={
                **native_fields,
                "reported_objective": objective,
                "recomputed_cost": cost,
            },
        )

    return solver_result(Solution(routes=routes, cost=cost), witness)
