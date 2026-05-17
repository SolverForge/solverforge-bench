from __future__ import annotations

from job_shop_bench.domain.models import JobShopInstance, Solution


class ValidationError(ValueError):
    pass


def validate(instance: JobShopInstance, solution: Solution) -> int:
    entries = {(op.job_id, op.op_index): op for job in instance.operations_by_job for op in job}
    seen = set()
    machine_windows: dict[int, list[tuple[int, int, tuple[int, int]]]] = {}
    starts: dict[tuple[int, int], int] = {}

    for sop in solution.operations:
        key = (sop.job_id, sop.op_index)
        if key not in entries:
            raise ValidationError(f"Unknown operation {key}")
        if key in seen:
            raise ValidationError(f"Duplicate operation {key}")
        if sop.start < 0:
            raise ValidationError(f"Negative start for {key}")
        src = entries[key]
        if sop.machine_id != src.machine_id or sop.duration != src.duration:
            raise ValidationError(f"Mismatched machine/duration for {key}")
        seen.add(key)
        starts[key] = sop.start
        machine_windows.setdefault(sop.machine_id, []).append((sop.start, sop.start + sop.duration, key))

    if seen != set(entries):
        missing = sorted(set(entries) - seen)
        raise ValidationError(f"Missing operations: {missing[:5]}")

    for job in instance.operations_by_job:
        for prev, cur in zip(job, job[1:]):
            if starts[(cur.job_id, cur.op_index)] < starts[(prev.job_id, prev.op_index)] + prev.duration:
                raise ValidationError(f"Precedence violation on job {cur.job_id}")

    for machine, windows in machine_windows.items():
        windows.sort(key=lambda x: x[0])
        for (_, end_a, key_a), (start_b, _, key_b) in zip(windows, windows[1:]):
            if start_b < end_a:
                raise ValidationError(f"Machine overlap on {machine}: {key_a} and {key_b}")

    return max(starts[(op.job_id, op.op_index)] + op.duration for job in instance.operations_by_job for op in job)
