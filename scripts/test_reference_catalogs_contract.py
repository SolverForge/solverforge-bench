#!/usr/bin/env python3.14
"""Regression tests for the reference catalogs and their warehouse resolution.

Three properties matter and each has a way to fail silently:

* every catalog reproduces from its pinned source, so a hand-edited value is
  caught rather than published;
* every bundled instance has a reference, so a gap is never computed against a
  missing value;
* the warehouse resolves a catalog value as the effective reference for rows
  already stored, so existing evidence gains references instead of needing a
  re-run.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]

CATALOGS = {
    "cvrp": (
        ROOT / "list-variable/cvrp/data/X",
        "CVRPLIB-X",
        ROOT / "list-variable/cvrp/data/X/references.json",
    ),
    "job-shop-scheduling": (
        ROOT / "scalar-variable/job-shop-scheduling/data/jsplib",
        "JSPLIB",
        ROOT / "scalar-variable/job-shop-scheduling/data/jsplib/references.json",
    ),
    "employee-scheduling": (
        ROOT / "scalar-variable/employee-scheduling/data/inrc2",
        "INRC-II",
        ROOT / "scalar-variable/employee-scheduling/data/inrc2/references.json",
    ),
}


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReferenceCatalogContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT / "src"))
        cls.catalogs = {
            name: json.loads(path.read_text())
            for name, (_, _, path) in CATALOGS.items()
        }

    def test_every_catalog_names_the_source_it_came_from(self) -> None:
        for name, catalog in self.catalogs.items():
            with self.subTest(problem=name):
                source = catalog["source"]
                self.assertTrue(str(source.get("name", "")).strip())
                self.assertTrue(str(source.get("revision", "")).strip())

    def test_every_instance_the_problem_runs_has_a_reference(self) -> None:
        """A run must never compute a gap against a missing value.

        Every instance the problem can run resolves a reference, except the
        employee-scheduling selection outside the published test set, where the
        absence is the honest answer and is reported rather than filled.
        """
        generator = _load_module(
            ROOT / "scripts/generate_reference_catalog.py",
            "gen_reference_catalog_coverage",
        )
        for name, (data_dir, _dataset, path) in CATALOGS.items():
            with self.subTest(problem=name):
                catalog = self.catalogs[name]
                if name == "cvrp":
                    bundled = {p.stem for p in data_dir.glob("*.vrp")}
                elif name == "job-shop-scheduling":
                    bundled = set(
                        json.loads((data_dir / "manifest.json").read_text())["groups"][
                            "canonical"
                        ]
                    )
                else:
                    # The employee catalog covers two published sources whose
                    # tuples differ: the reference solutions the corpus ships,
                    # and the scores the competition validated across finalists.
                    # Every key must still name a case the corpus can enumerate.
                    enumerated = generator.enumerable_case_names()
                    self.assertTrue(
                        set(catalog["instances"]) <= enumerated,
                        "the employee catalog names cases the loader cannot enumerate: "
                        f"{sorted(set(catalog['instances']) - enumerated)[:5]}",
                    )
                    self.assertGreaterEqual(len(catalog["instances"]), 9)
                    continue
                self.assertEqual(
                    set(catalog["instances"]),
                    bundled,
                    f"{name}: catalog and bundled instances disagree",
                )

    def test_employee_solution_directories_are_well_formed(self) -> None:
        """A directory carrying solution rows must match the weeks it names."""
        generator = _load_module(
            ROOT / "scripts/generate_reference_catalog.py",
            "gen_reference_catalog_files",
        )
        shipped = generator.employee_reference_instances()
        for name, (sol_dir, weeks) in shipped.items():
            with self.subTest(instance=name):
                solution_dir = Path(sol_dir)
                self.assertTrue(solution_dir.is_dir(), f"{name}: {sol_dir} is gone")
                rows = sorted(solution_dir.glob("Sol-*.txt"))
                self.assertEqual(len(rows), len(weeks), f"{name}: week rows differ")

    def test_published_reference_cases_are_enumerable(self) -> None:
        """A published reference must belong to a case the loader can produce.

        The catalog key and the loader's case name are written in different
        styles, so a key that no run can produce would hold a reference nothing
        could ever resolve against.
        """
        generator = _load_module(
            ROOT / "scripts/generate_reference_catalog.py", "gen_reference_catalog_pub"
        )
        catalog = self.catalogs["employee-scheduling"]["instances"]
        published = {
            name
            for name, entry in catalog.items()
            if str(entry.get("reference_detail", "")).startswith("best validated")
        }
        self.assertTrue(published, "no competition-validated references are published")
        enumerated = generator.enumerable_case_names()
        self.assertEqual(
            published - enumerated,
            set(),
            "published references name cases the loader cannot enumerate",
        )

    def test_reference_kind_is_explicit_and_valid(self) -> None:
        for name, catalog in self.catalogs.items():
            for instance, entry in catalog["instances"].items():
                with self.subTest(problem=name, instance=instance):
                    kind = entry.get("kind") or (
                        "known_optimum"
                        if entry["status"] == "closed"
                        else "best_known_upper_bound"
                    )
                    self.assertIn(kind, ("known_optimum", "best_known_upper_bound"))
                    self.assertGreater(entry["reference"], 0)

    def test_catalogs_reproduce_from_their_pinned_sources(self) -> None:
        """A hand-edited value must fail the gate, not reach the page."""
        generator = _load_module(
            ROOT / "scripts/generate_reference_catalog.py", "gen_reference_catalog"
        )
        self.assertEqual(generator.generate_jssp(check=True), 0)
        self.assertEqual(
            generator.generate_cvrp(
                check=True, table_path=generator.DEFAULT_CVRP_TABLE
            ),
            0,
        )
        self.assertEqual(generator.generate_employee(check=True), 0)

    def test_cvrplib_optimum_column_decides_the_reference_kind(self) -> None:
        generator = _load_module(
            ROOT / "scripts/generate_reference_catalog.py", "gen_reference_catalog_kind"
        )
        parsed = generator.parse_cvrplib_table(
            "X-n101-k25 100 25 206 27,591.00 yes\n"
            "X-n1001-k43 1000 43 131 72,346.00 no\n"
        )
        self.assertEqual(parsed["X-n101-k25"]["status"], "closed")
        self.assertEqual(parsed["X-n1001-k43"]["status"], "open")
        self.assertEqual(parsed["X-n101-k25"]["reference"], 27591.0)

    def test_loader_exposes_every_catalog_value_for_the_warehouse(self) -> None:
        loader = _load_module(
            ROOT / "scripts/load_reference_catalog.py", "load_reference_catalog"
        )
        rows = loader.catalog_rows()
        by_problem: dict[str, int] = {}
        for benchmark_name, _dataset, _instance, *_rest in rows:
            by_problem[benchmark_name] = by_problem.get(benchmark_name, 0) + 1
        for name, (_, _, path) in CATALOGS.items():
            with self.subTest(problem=name):
                expected = len(json.loads(path.read_text())["instances"])
                self.assertEqual(by_problem[name], expected)

    def test_loader_sql_escapes_quotes(self) -> None:
        loader = _load_module(
            ROOT / "scripts/load_reference_catalog.py", "load_reference_catalog_sql"
        )
        self.assertEqual(loader._literal("it's"), "'it''s'")
        sql = loader.build_sql(
            [("p", "d", "i", 1.0, "known_optimum", "it's source", "rev")]
        )
        self.assertIn("'it''s source'", sql)
        self.assertIn("BEGIN;", sql)
        self.assertIn("ON CONFLICT", sql)


if __name__ == "__main__":
    unittest.main()
