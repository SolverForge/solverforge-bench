from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from solverforge import (
    ConstraintFactory,
    HardSoftScore,
    Solver,
    constraint_provider,
    planning_entity,
    planning_list_variable,
    planning_solution,
    problem_fact,
)

from job_shop_bench.domain.models import (
    JobShopInstance,
    ScheduledOperation,
    Solution,
)
from job_shop_bench.solver.instance_json import serialize_instance
from solverforge_bench.fair_start import (
    emit_fair_start_witness,
    make_fair_start_witness,
    solver_result,
)
from solverforge_bench.model import SolverResult
from solverforge_bench.solverforge_config import solver_config_for_time_limit


_SOLVER_CONFIG_PATH = Path(__file__).with_name("solverforge_py.toml")


def _operation_owner(solution: Any, operation_id: int) -> int:
    return int(solution.operation_facts[operation_id].machine_id)


def _operation_construction_order(solution: Any, operation_id: int) -> int:
    fact = solution.operation_facts[int(operation_id)]
    return int(fact.op_index) * 1_000_000 - int(fact.duration)


def _operation_duration(solution: Any, operation_id: int) -> int:
    return int(solution.operation_facts[int(operation_id)].duration)


def _operation_successors(solution: Any, operation_id: int) -> list[int]:
    successor_id = solution.operation_facts[int(operation_id)].successor_id
    return [] if successor_id is None else [int(successor_id)]


@problem_fact
class OperationFact:
    def __init__(
        self,
        *,
        operation_id: int,
        job_id: int,
        op_index: int,
        machine_id: int,
        duration: int,
        successor_id: int | None,
    ) -> None:
        self.operation_id = operation_id
        self.job_id = job_id
        self.op_index = op_index
        self.machine_id = machine_id
        self.duration = duration
        self.successor_id = successor_id


@planning_entity
class MachineSequence:
    operations = planning_list_variable(
        element_collection="operation_indices",
        element_owner=_operation_owner,
        construction_element_order_key=_operation_construction_order,
        precedence_duration=_operation_duration,
        precedence_successors=_operation_successors,
    )

    def __init__(self, machine_id: int) -> None:
        self.machine_id = machine_id
        self.operations: list[int] = []


@constraint_provider
def _jssp_constraints(factory: ConstraintFactory) -> list[object]:
    return [
        factory.list_precedence_makespan(MachineSequence, "operations").named(
            "jssp schedule"
        )
    ]


@planning_solution(
    score=HardSoftScore,
    constraints=_jssp_constraints,
)
class JobShopPythonPlan:
    machine_sequences: list[MachineSequence]
    operation_facts: list[OperationFact]

    def __init__(self, instance: JobShopInstance) -> None:
        self.machine_sequences = [
            MachineSequence(machine_id) for machine_id in range(instance.num_machines)
        ]
        flat_operations = [op for job in instance.operations_by_job for op in job]
        operation_id_by_key = {
            (int(op.job_id), int(op.op_index)): operation_id
            for operation_id, op in enumerate(flat_operations)
        }
        self.operation_facts = [
            OperationFact(
                operation_id=operation_id,
                job_id=op.job_id,
                op_index=op.op_index,
                machine_id=op.machine_id,
                duration=op.duration,
                successor_id=operation_id_by_key.get(
                    (int(op.job_id), int(op.op_index) + 1)
                ),
            )
            for operation_id, op in enumerate(flat_operations)
        ]
        self.operation_indices = list(range(len(self.operation_facts)))
        self.score = None


def solve_with_solverforge_py(
    instance: JobShopInstance, time_limit: int
) -> SolverResult:
    instance_json = serialize_instance(instance)
    witness = make_fair_start_witness(
        benchmark_name="job-shop-scheduling",
        solver="solverforge-py",
        planning_state="empty_list_variables",
        solver_input=instance_json,
    )
    plan = JobShopPythonPlan(instance)
    config = _solver_config(time_limit)

    emit_fair_start_witness(witness)
    solved = Solver.solve(plan, config)

    operations, makespan = _scheduled_operations(
        solved.machine_sequences, solved.operation_facts
    )
    return solver_result(
        Solution(operations=tuple(operations), reported_makespan=makespan),
        witness,
    )


def _scheduled_operations(
    machine_sequences: list[Any],
    operation_facts: list[Any],
) -> tuple[list[ScheduledOperation], int | None]:
    metrics = _schedule_metrics(machine_sequences, operation_facts)
    starts = metrics["starts"]
    output: list[ScheduledOperation] = []
    for machine in machine_sequences:
        for operation_id in machine.operations:
            operation_id = int(operation_id)
            if not 0 <= operation_id < len(operation_facts):
                continue
            fact = operation_facts[operation_id]
            output.append(
                ScheduledOperation(
                    job_id=int(fact.job_id),
                    op_index=int(fact.op_index),
                    machine_id=int(machine.machine_id),
                    start=int(starts.get(operation_id, 0)),
                    duration=int(fact.duration),
                )
            )
    makespan = None if metrics["cycle_penalty"] else int(metrics["makespan"])
    return output, makespan


def _schedule_metrics(
    machine_sequences: list[Any],
    operation_facts: list[Any],
) -> dict[str, Any]:
    assigned_order: list[int] = []
    assigned_by_machine: dict[int, list[int]] = {}
    for machine in machine_sequences:
        sequence = [int(operation_id) for operation_id in machine.operations]
        assigned_by_machine[int(machine.machine_id)] = sequence
        assigned_order.extend(sequence)

    valid_assigned = [
        operation_id
        for operation_id in assigned_order
        if 0 <= operation_id < len(operation_facts)
    ]
    duplicate_penalty = len(valid_assigned) - len(set(valid_assigned))
    active_ids = set(valid_assigned)
    edges: dict[int, set[int]] = defaultdict(set)
    indegree = {operation_id: 0 for operation_id in active_ids}

    by_job: dict[int, list[Any]] = defaultdict(list)
    for fact in operation_facts:
        by_job[int(fact.job_id)].append(fact)
    for job_ops in by_job.values():
        job_ops.sort(key=lambda fact: int(fact.op_index))
        for left, right in zip(job_ops, job_ops[1:]):
            left_id = int(left.operation_id)
            right_id = int(right.operation_id)
            if left_id in active_ids and right_id in active_ids:
                _add_edge(edges, indegree, left_id, right_id)

    for sequence in assigned_by_machine.values():
        cleaned = [
            operation_id
            for operation_id in sequence
            if 0 <= operation_id < len(operation_facts)
        ]
        for left_id, right_id in zip(cleaned, cleaned[1:]):
            _add_edge(edges, indegree, left_id, right_id)

    queue = deque(
        sorted(operation_id for operation_id, degree in indegree.items() if degree == 0)
    )
    starts = {operation_id: 0 for operation_id in active_ids}
    visited = 0
    while queue:
        operation_id = queue.popleft()
        visited += 1
        finish = starts[operation_id] + int(operation_facts[operation_id].duration)
        for target in sorted(edges.get(operation_id, ())):
            starts[target] = max(starts[target], finish)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    cycle_penalty = len(active_ids) - visited
    makespan = (
        max(
            (
                starts[operation_id] + int(operation_facts[operation_id].duration)
                for operation_id in active_ids
            ),
            default=0,
        )
        if not cycle_penalty
        else 0
    )
    return {
        "starts": starts,
        "makespan": makespan,
        "cycle_penalty": cycle_penalty,
        "duplicate_penalty": duplicate_penalty,
    }


def _add_edge(
    edges: dict[int, set[int]],
    indegree: dict[int, int],
    left_id: int,
    right_id: int,
) -> None:
    if left_id == right_id or right_id in edges[left_id]:
        return
    edges[left_id].add(right_id)
    indegree[right_id] += 1


def _solver_config(time_limit: int) -> dict[str, Any]:
    return solver_config_for_time_limit(_SOLVER_CONFIG_PATH, time_limit)
