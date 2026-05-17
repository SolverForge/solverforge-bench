from __future__ import annotations

import json

from job_shop_bench.domain.models import JobShopInstance


def serialize_instance(instance: JobShopInstance) -> str:
    operations = [
        {
            "job_id": op.job_id,
            "op_index": op.op_index,
            "machine_id": op.machine_id,
            "duration": op.duration,
        }
        for job in instance.operations_by_job
        for op in job
    ]
    return json.dumps(
        {
            "name": instance.name,
            "family": instance.family,
            "num_jobs": instance.num_jobs,
            "num_machines": instance.num_machines,
            "operations": operations,
        }
    )
