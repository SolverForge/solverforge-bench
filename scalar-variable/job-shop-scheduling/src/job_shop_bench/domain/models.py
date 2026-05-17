from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Operation:
    job_id: int
    op_index: int
    machine_id: int
    duration: int


@dataclass(frozen=True)
class JobShopInstance:
    name: str
    family: str
    num_jobs: int
    num_machines: int
    operations_by_job: tuple[tuple[Operation, ...], ...]


@dataclass(frozen=True)
class ScheduledOperation:
    job_id: int
    op_index: int
    machine_id: int
    start: int
    duration: int


@dataclass(frozen=True)
class Solution:
    operations: tuple[ScheduledOperation, ...]
    reported_makespan: int | None = None
