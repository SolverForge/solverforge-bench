from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


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


class ScheduledOperation(BaseModel):
    job_id: int
    op_index: int
    machine_id: int
    start: int
    duration: int


class Solution(BaseModel):
    operations: tuple[ScheduledOperation, ...]
    reported_makespan: int | None = None
