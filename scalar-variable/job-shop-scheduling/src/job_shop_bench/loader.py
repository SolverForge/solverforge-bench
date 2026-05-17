from __future__ import annotations

import json
from pathlib import Path

from job_shop_bench.domain.models import JobShopInstance, Operation


def load_manifest(data_dir: Path) -> dict:
    return json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))


def dataset_group_names(data_dir: Path, group: str) -> set[str]:
    manifest = load_manifest(data_dir)
    groups = manifest.get("groups", {})
    if group not in groups:
        raise ValueError(f"Unknown dataset set '{group}'. Available: {', '.join(sorted(groups))}")
    return set(groups[group])


def instance_metadata(data_dir: Path) -> dict[str, dict]:
    manifest = load_manifest(data_dir)
    return {item["name"]: item for item in manifest.get("instances", [])}


def load_instance(path: Path, *, name: str, family: str) -> JobShopInstance:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    num_jobs, num_machines = [int(x) for x in lines[0].split()[:2]]
    ops_by_job: list[tuple[Operation, ...]] = []
    for job_id, row in enumerate(lines[1:1 + num_jobs]):
        vals = [int(x) for x in row.split()]
        ops = []
        for op_index in range(0, len(vals), 2):
            machine_id = vals[op_index]
            duration = vals[op_index + 1]
            ops.append(Operation(job_id=job_id, op_index=op_index // 2, machine_id=machine_id, duration=duration))
        ops_by_job.append(tuple(ops))
    return JobShopInstance(name=name, family=family, num_jobs=num_jobs, num_machines=num_machines, operations_by_job=tuple(ops_by_job))
