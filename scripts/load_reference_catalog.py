#!/usr/bin/env python3.14
"""Load each problem's pinned reference catalog into the warehouse.

The catalogs are generated from their official sources by
``generate_reference_catalog.py`` and committed beside the instances they
describe. Every benchmark run opened with ``--save-postgres`` already syncs the
warehouse to them; this script performs the same sync on demand, through the
same warehouse function (``benchmark_sync_reference_catalog``), for instance
right after a refreshed catalog lands and before the next run.

It reads only the catalogs and writes only the catalog tables. It never runs a
benchmark and never touches results.

    scripts/load_reference_catalog.py [--database-url URL] [--check]

``--check`` reports what would be loaded without writing.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from solverforge_bench.pins import (  # noqa: E402
    reference_catalog_snapshot,
    sync_reference_catalog,
)

DEFAULT_DATABASE_URL = "postgresql://postgres@localhost/solverforge_bench"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("BENCH_DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--check", action="store_true", help="report, do not write")
    args = parser.parse_args(argv)

    snapshot = reference_catalog_snapshot(ROOT)
    counts = snapshot.counts()

    if args.check:
        for name, count in sorted(counts.items()):
            print(f"{name}: {count} reference values ready to load")
        return 0

    import psycopg

    with psycopg.connect(args.database_url, autocommit=True) as conn:
        digest = sync_reference_catalog(conn, snapshot)
    for name, count in sorted(counts.items()):
        print(f"{name}: {count} reference values loaded")
    print(f"reference catalog version {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
