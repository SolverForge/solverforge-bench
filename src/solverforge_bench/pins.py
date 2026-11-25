"""What a run is measured against: the reference catalog and the instances.

The repository is the only source of both. When a run opens, the warehouse is
brought to the committed reference catalog and records the catalog version the
run is graded against, then records the input hash of every instance the run
loads. Both writes go through warehouse functions
(``benchmark_sync_reference_catalog`` and ``benchmark_record_run_instances``),
so the manual loader and the run path share one implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from solverforge_bench.model import BenchmarkCase
from solverforge_bench.references import load_catalog, reference_for

#: Each problem's committed catalog and the dataset name its results record.
REFERENCE_CATALOGS: tuple[tuple[str, str, str], ...] = (
    ("cvrp", "CVRPLIB-X", "list-variable/cvrp/data/X"),
    (
        "job-shop-scheduling",
        "JSPLIB",
        "scalar-variable/job-shop-scheduling/data/jsplib",
    ),
    (
        "employee-scheduling",
        "INRC-II",
        "scalar-variable/employee-scheduling/data/inrc2",
    ),
)


@dataclass(frozen=True)
class ReferenceCatalogSnapshot:
    """The committed catalogs in the shape the warehouse stores."""

    entries: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]

    def counts(self) -> dict[str, int]:
        by_problem: dict[str, int] = {}
        for entry in self.entries:
            name = entry["benchmark_name"]
            by_problem[name] = by_problem.get(name, 0) + 1
        return by_problem


def reference_catalog_snapshot(repo_root: Path) -> ReferenceCatalogSnapshot:
    """Read every committed catalog, resolving kinds exactly as evaluation does."""
    entries: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for benchmark_name, dataset, relative_dir in REFERENCE_CATALOGS:
        data_dir = Path(repo_root) / relative_dir
        catalog = load_catalog(str(data_dir))
        source = catalog["source"]
        sources.append(
            {
                "benchmark_name": benchmark_name,
                "dataset": dataset,
                "catalog": f"{relative_dir}/references.json",
                "source_name": str(source["name"]),
                "source_revision": str(source["revision"]),
                "url": source.get("url"),
            }
        )
        for instance in sorted(catalog["instances"]):
            reference = reference_for(data_dir, instance)
            entries.append(
                {
                    "benchmark_name": benchmark_name,
                    "dataset": dataset,
                    "instance": instance,
                    "reference_cost": reference.reference_cost,
                    "reference_kind": reference.kind,
                    "source_name": reference.source_name,
                    "source_revision": reference.source_revision,
                }
            )
    if not entries:
        raise ValueError("the committed reference catalogs carry no entries")
    return ReferenceCatalogSnapshot(entries=tuple(entries), sources=tuple(sources))


def sync_reference_catalog(conn: Any, snapshot: ReferenceCatalogSnapshot) -> str:
    """Bring the warehouse to ``snapshot`` and return its catalog version hash."""
    from psycopg.types.json import Jsonb

    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "SELECT benchmark_sync_reference_catalog(%s, %s)",
            (Jsonb(list(snapshot.entries)), Jsonb(list(snapshot.sources))),
        )
        digest = cur.fetchone()[0]
    return str(digest)


def run_instance_records(
    cases: Iterable[BenchmarkCase], input_hashes: dict[tuple[str, str, str], str]
) -> list[dict[str, Any]]:
    """One record per case: its identity, size, and solver-input hash."""
    records = []
    for case in cases:
        key = case_key(case)
        records.append(
            {
                "dataset": case.dataset,
                "dataset_set": case.dataset_set,
                "instance": case.instance,
                "instance_size": case.instance_size,
                "input_sha256": input_hashes[key],
            }
        )
    return records


def record_run_instances(conn: Any, run_id: Any, records: list[dict[str, Any]]) -> int:
    """Pin the instance hashes of an opened run."""
    from psycopg.types.json import Jsonb

    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "SELECT benchmark_record_run_instances(%s, %s)",
            (run_id, Jsonb(records)),
        )
        recorded = cur.fetchone()[0]
    return int(recorded)


def case_key(case: BenchmarkCase) -> tuple[str, str, str]:
    return (case.dataset, case.dataset_set, case.instance)
