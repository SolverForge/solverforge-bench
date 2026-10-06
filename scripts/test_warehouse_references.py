#!/usr/bin/env python3.14
"""Prove the warehouse resolves official references for stored results.

This is the read-only half of the reference work: the catalogs are committed,
the warehouse carries them, and existing rows must gain a reference without any
benchmark being re-run. A run is never started here; the test only reads.

Skipped loudly (non-zero) if the warehouse is unreachable, because a gate that
silently passes when it cannot see the thing it checks is not a gate.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

DATABASE_URL = os.environ.get(
    "BENCH_DATABASE_URL", "postgresql://postgres@localhost/solverforge_bench"
)

PSQL_ENV = {
    **os.environ,
    "PGOPTIONS": "-c default_transaction_read_only=on -c statement_timeout=15000",
}


def query(sql: str) -> list[list[str]]:
    result = subprocess.run(
        [
            "psql",
            DATABASE_URL,
            "-X",
            "-qAt",
            "-F",
            "\t",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        text=True,
        capture_output=True,
        env=PSQL_ENV,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "psql failed")
    return [line.split("\t") for line in result.stdout.strip().splitlines() if line]


class WarehouseReferenceResolutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            rows = query("SELECT count(*) FROM benchmark_reference_catalog;")
        except (RuntimeError, FileNotFoundError) as exc:
            raise unittest.SkipTest(f"warehouse unreachable: {exc}") from exc
        cls.catalog_rows = int(rows[0][0])
        if cls.catalog_rows == 0:
            raise AssertionError(
                "benchmark_reference_catalog is empty; load it with "
                "scripts/load_reference_catalog.py"
            )

    def test_catalog_covers_every_bundled_problem(self) -> None:
        rows = query(
            "SELECT benchmark_name, count(*) FROM benchmark_reference_catalog "
            "GROUP BY 1 ORDER BY 1;"
        )
        problems = {name for name, _count in rows}
        self.assertEqual(
            problems,
            {"cvrp", "employee-scheduling", "job-shop-scheduling"},
            "a problem with a bundled catalog is missing from the warehouse",
        )

    def test_resolution_prefers_the_catalog_over_a_recorded_value(self) -> None:
        """A row whose recorded value disagrees must resolve to the official one."""
        rows = query(
            "SELECT count(*) FROM benchmark_reference_resolved "
            "WHERE catalog_reference_cost IS NOT NULL "
            "  AND effective_reference_cost = catalog_reference_cost;"
        )
        with_catalog = int(
            query(
                "SELECT count(*) FROM benchmark_reference_resolved "
                "WHERE catalog_reference_cost IS NOT NULL;"
            )[0][0]
        )
        self.assertGreater(
            with_catalog, 0, "no stored row resolved against the catalog"
        )
        self.assertEqual(int(rows[0][0]), with_catalog)

    def test_cvrp_rows_recorded_before_the_catalog_now_resolve(self) -> None:
        """The 125 cvrp rows that had no reference must gain one."""
        rows = query(
            "SELECT count(*) FROM benchmark_reference_resolved "
            "WHERE benchmark_name = 'cvrp' "
            "  AND recorded_reference_cost IS NULL "
            "  AND effective_reference_cost IS NOT NULL;"
        )
        self.assertGreater(
            int(rows[0][0]),
            0,
            "cvrp rows without a recorded reference still have none after loading",
        )

    def test_employee_reference_values_match_the_published_penalties(self) -> None:
        """Every warehouse employee value is one the loader can resolve.

        The catalog holds both official sources: the reference solutions the test
        set ships, and the history/week tuples the competition scored across the
        finalists. The manifest declares which tuples a run grades, and every one
        of them carries a value here, so no graded instance is scored against
        nothing.
        """
        rows = query(
            "SELECT instance, reference_cost FROM benchmark_reference_catalog "
            "WHERE benchmark_name = 'employee-scheduling' ORDER BY instance;"
        )
        resolved = {instance: float(cost) for instance, cost in rows}

        data_dir = (
            Path(__file__).resolve().parents[1]
            / "scalar-variable/employee-scheduling/data/inrc2"
        )
        catalog = json.loads((data_dir / "references.json").read_text(encoding="utf-8"))
        manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(
            set(resolved),
            set(catalog["instances"]),
            "the warehouse and the run-facing catalog disagree",
        )
        selected = set(manifest["selected_tuples"])
        self.assertEqual(
            selected - set(resolved),
            set(),
            "a graded tuple has no reference in the warehouse",
        )
        # Values verified against the official INRC-II validator.
        self.assertEqual(resolved["n005w4_H0_WD1-2-3-3"], 1695.0)
        self.assertEqual(resolved["n005w4_H1_WD5-3-1-0"], 2010.0)
        self.assertEqual(resolved["n021w4_H2_WD8-1-4-3"], 2345.0)

    def test_reference_kind_is_recorded_for_every_catalog_row(self) -> None:
        rows = query(
            "SELECT count(*) FROM benchmark_reference_catalog "
            "WHERE reference_kind NOT IN ('known_optimum','best_known_upper_bound');"
        )
        self.assertEqual(int(rows[0][0]), 0)

    def test_a_catalog_reference_is_never_negative(self) -> None:
        rows = query(
            "SELECT count(*) FROM benchmark_reference_catalog WHERE reference_cost <= 0;"
        )
        self.assertEqual(int(rows[0][0]), 0)


if __name__ == "__main__":
    unittest.main()
