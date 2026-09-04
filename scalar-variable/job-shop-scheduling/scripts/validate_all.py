from __future__ import annotations

from pathlib import Path

from job_shop_bench.loader import instance_metadata, load_instance
from job_shop_bench.references import load_reference_catalog


def main() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data" / "jsplib"
    meta = instance_metadata(data_dir)
    references = load_reference_catalog(str(data_dir))["instances"]
    assert set(references) == set(meta)
    for name, item in sorted(meta.items()):
        inst = load_instance(data_dir / item["path"], name=name, family=item["family"])
        assert inst.num_jobs > 0 and inst.num_machines > 0
        assert all(len(job) == inst.num_machines for job in inst.operations_by_job)
        reference = references[name]
        assert reference["lower_bound"] <= reference["upper_bound"]
        assert reference["status"] in {"closed", "open"}
    print(f"validated {len(meta)} instances and {len(references)} official references")


if __name__ == "__main__":
    main()
