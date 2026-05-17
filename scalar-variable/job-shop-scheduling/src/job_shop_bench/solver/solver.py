from __future__ import annotations

from typing import Callable

from job_shop_bench.domain.models import JobShopInstance, ScheduledOperation, Solution
from solverforge_bench.model import SolverVersion

AVAILABLE_METHODS = ["solverforge"]


def create_solver(method: str, time_limit: int) -> Callable[[JobShopInstance, int], Solution]:
    if method != "solverforge":
        raise ValueError(f"Unknown solver: {method}")

    def solve(instance: JobShopInstance, _time_limit: int) -> Solution:
        # Deterministic earliest-start dispatch baseline.
        machine_ready = [0] * instance.num_machines
        job_ready = [0] * instance.num_jobs
        out: list[ScheduledOperation] = []
        for job in instance.operations_by_job:
            for op in job:
                start = max(job_ready[op.job_id], machine_ready[op.machine_id])
                out.append(ScheduledOperation(job_id=op.job_id, op_index=op.op_index, machine_id=op.machine_id, start=start, duration=op.duration))
                finish = start + op.duration
                job_ready[op.job_id] = finish
                machine_ready[op.machine_id] = finish
        makespan = max(job_ready) if job_ready else 0
        return Solution(operations=tuple(out), reported_makespan=makespan)

    return solve


def solver_versions(solvers: list[str]) -> dict[str, SolverVersion]:
    return {s: SolverVersion(solver=s, version="baseline-dispatch", source="benchmark") for s in solvers}
