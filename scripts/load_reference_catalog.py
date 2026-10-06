#!/usr/bin/env python3.14
"""Load each problem's pinned reference catalog into the warehouse.

The catalogs are generated from their official sources by
``generate_reference_catalog.py`` and committed beside the instances they
describe. This script is the other half: it carries those committed values into
``benchmark_reference_catalog`` so warehouse views resolve a reference for every
result, including rows written before the catalog existed.

It reads only the catalogs and writes only the catalog table. It never runs a
benchmark and never touches results.

    scripts/load_reference_catalog.py [--database-url URL] [--check]

``--check`` reports what would change without writing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]

#: Each problem's catalog and the dataset its results record.
CATALOGS = (
    ("cvrp", "CVRPLIB-X", ROOT / "list-variable/cvrp/data/X/references.json"),
    (
        "job-shop-scheduling",
        "JSPLIB",
        ROOT / "scalar-variable/job-shop-scheduling/data/jsplib/references.json",
    ),
    (
        "employee-scheduling",
        "INRC-II",
        ROOT / "scalar-variable/employee-scheduling/data/inrc2/references.json",
    ),
)

DEFAULT_DATABASE_URL = "postgresql://postgres@localhost/solverforge_bench"


def catalog_rows() -> list[tuple[str, str, str, float, str, str, str]]:
    rows = []
    for benchmark_name, dataset, path in CATALOGS:
        if not path.exists():
            raise SystemExit(
                f"{path} is missing; generate it with "
                f"scripts/generate_reference_catalog.py before loading"
            )
        catalog = json.loads(path.read_text(encoding="utf-8"))
        source = catalog["source"]
        for instance, entry in sorted(catalog["instances"].items()):
            rows.append(
                (
                    benchmark_name,
                    dataset,
                    instance,
                    float(entry["reference"]),
                    (
                        entry["kind"]
                        if "kind" in entry
                        else (
                            "known_optimum"
                            if entry["status"] == "closed"
                            else "best_known_upper_bound"
                        )
                    ),
                    str(source["name"]),
                    str(source["revision"]),
                )
            )
    return rows


def build_sql(rows: list[tuple]) -> str:
    """One upsert per row, in a single transaction.

    The values are generated and committed, so a re-run is a no-op; an updated
    catalog rewrites its rows rather than accumulating near-duplicates.
    """
    values = ",\n".join(
        "    ({}, {}, {}, {}, {}, {}, {})".format(
            _literal(name),
            _literal(dataset),
            _literal(instance),
            repr(float(cost)),
            _literal(kind),
            _literal(source),
            _literal(revision),
        )
        for name, dataset, instance, cost, kind, source, revision in rows
    )
    keys = ",\n".join(
        "    ({}, {}, {})".format(_literal(name), _literal(dataset), _literal(instance))
        for name, dataset, instance, *_rest in rows
    )
    return f"""
BEGIN;
SET LOCAL statement_timeout = '120s';
INSERT INTO benchmark_reference_catalog (
    benchmark_name, dataset, instance, reference_cost, reference_kind,
    source_name, source_revision
) VALUES
{values}
ON CONFLICT (benchmark_name, dataset, instance) DO UPDATE SET
    reference_cost = EXCLUDED.reference_cost,
    reference_kind = EXCLUDED.reference_kind,
    source_name = EXCLUDED.source_name,
    source_revision = EXCLUDED.source_revision;
-- The committed catalogs are the authority for what the warehouse may resolve.
-- A row for an instance no catalog still carries would let a lookup succeed for
-- a case the loader cannot enumerate, so remove anything the catalogs dropped
-- instead of leaving a stale value in place.
DELETE FROM benchmark_reference_catalog
WHERE (benchmark_name, dataset, instance) NOT IN (
{keys}
);
COMMIT;
"""


def _literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("BENCH_DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--check", action="store_true", help="report, do not write")
    args = parser.parse_args(argv)

    rows = catalog_rows()
    if not rows:
        raise SystemExit("no catalog rows to load")
    by_problem: dict[str, int] = {}
    for name, _dataset, _instance, *_rest in rows:
        by_problem[name] = by_problem.get(name, 0) + 1

    if args.check:
        for name, count in sorted(by_problem.items()):
            print(f"{name}: {count} reference values ready to load")
        return 0

    response = subprocess.run(
        ["psql", args.database_url, "-X", "-q", "-v", "ON_ERROR_STOP=1"],
        input=build_sql(rows),
        text=True,
        capture_output=True,
    )
    if response.returncode != 0:
        sys.stderr.write(response.stdout)
        sys.stderr.write(response.stderr)
        raise SystemExit("loading the reference catalog failed")
    for name, count in sorted(by_problem.items()):
        print(f"{name}: {count} reference values loaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
