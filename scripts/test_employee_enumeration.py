#!/usr/bin/env python3.14
"""Regression tests for the employee-scheduling case enumeration.

The loader decides which (instance, history, week) tuples exist. Two families of
tuple have to coexist:

* the default selection, which takes the leading weeks of each family; and
* the tuples the competition published validated results for, whose week sets are
  arbitrary subsets such as ``WD6-2-9-1`` rather than ``WD0-1-2-3``.

The second family was unreachable because enumeration assumed leading weeks, so
the competition's validated scores had no case to resolve against. These tests
pin that a shipped solution's exact week set is enumerable, that the default
selection is unchanged, and that a tuple the corpus cannot support is not
invented.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DATA_DIR = ROOT / "scalar-variable/employee-scheduling/data/inrc2"

from employee_scheduling_bench.loader import (  # noqa: E402
    enumerate_instances,
    load_instance,
)

TUPLE = re.compile(r"^(?P<instance>n\d+w\d+)_H(?P<history>\d+)_WD(?P<weeks>[\d-]+)$")


class EmployeeEnumerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = enumerate_instances(str(DATA_DIR))
        cls.names = {case["name"] for case in cls.cases}
        cls.references = json.loads((DATA_DIR / "references.json").read_text())
        cls.solution_dirs = sorted(
            path
            for family in DATA_DIR.glob("n*")
            if family.is_dir()
            for path in family.glob("Solution_H_*")
        )

    def test_every_shipped_solution_directory_is_enumerable(self) -> None:
        for solution_dir in self.solution_dirs:
            match = re.match(
                r"^Solution_H_(?P<history>\d+)-WD_(?P<weeks>[\d-]+)$",
                solution_dir.name,
            )
            self.assertIsNotNone(match, solution_dir.name)
            name = (
                f"{solution_dir.parent.name}_H{match.group('history')}"
                f"_WD{match.group('weeks')}"
            )
            with self.subTest(instance=name):
                self.assertIn(name, self.names)

    def test_validated_tuples_that_ship_a_solution_become_enumerable(self) -> None:
        """A published reference needs a case, even when its weeks are not leading."""
        manifest = json.loads((DATA_DIR / "manifest.json").read_text())
        selected = manifest["selected_tuples"]
        non_leading = [
            name
            for name in selected
            if not name.endswith(("_WD0-1-2-3", "_WD0-1-2-3-4-5-6-7"))
        ]

        self.assertTrue(non_leading, "no non-leading week set was exercised")
        for name in non_leading:
            with self.subTest(instance=name):
                self.assertIn(
                    name,
                    self.names,
                    "a selected tuple with shipped data is still not enumerable",
                )

    def test_every_selected_tuple_is_enumerable_and_carries_a_reference(self) -> None:
        """The selection is only meaningful if each tuple can be graded."""
        manifest = json.loads((DATA_DIR / "manifest.json").read_text())
        catalog = self.references["instances"]

        for name in manifest["selected_tuples"]:
            with self.subTest(instance=name):
                self.assertIn(name, self.names, "a selected tuple is not enumerable")
                self.assertIn(name, catalog, "a selected tuple has no reference")

    def test_an_enumerated_non_leading_tuple_actually_loads(self) -> None:
        """Enumeration is only useful if the case can be loaded and graded."""
        sample = "n030w4_H1_WD6-2-9-1"
        self.assertIn(sample, self.names)
        case = next(case for case in self.cases if case["name"] == sample)

        instance = load_instance(
            case["scenario_path"], case["history_path"], case["week_paths"]
        )

        self.assertEqual(
            len(instance.weeks), len(case["week_paths"]), "weeks were dropped"
        )
        self.assertEqual(case["num_weeks"], 4)
        self.assertEqual(
            [Path(path).name for path in case["week_paths"]],
            [f"WD-n030w4-{week}.txt" for week in ("6", "2", "9", "1")],
        )

    def test_default_leading_week_selection_is_unchanged(self) -> None:
        """Families without shipped solutions keep the leading-week selection."""
        leading = [
            case
            for case in self.cases
            if case["solution_dir"] is None
            and case["name"].endswith(("_WD0-1-2-3", "_WD0-1-2-3-4-5-6-7"))
        ]
        self.assertTrue(leading, "the default selection produced no leading-week cases")
        for case in leading:
            weeks = [Path(path).stem.rsplit("-", 1)[1] for path in case["week_paths"]]
            with self.subTest(instance=case["name"]):
                self.assertEqual(
                    weeks,
                    [str(index) for index in range(len(weeks))],
                    "the default selection no longer takes the leading weeks",
                )

    def test_no_case_is_invented_without_its_data(self) -> None:
        """Enumeration must never name a case the corpus cannot load."""
        for case in self.cases:
            with self.subTest(instance=case["name"]):
                self.assertTrue(Path(case["scenario_path"]).is_file())
                self.assertTrue(Path(case["history_path"]).is_file())
                self.assertTrue(case["week_paths"], "a case has no week data")
                for path in case["week_paths"]:
                    self.assertTrue(Path(path).is_file(), path)

    def test_every_case_name_is_unique(self) -> None:
        names = [case["name"] for case in self.cases]
        self.assertEqual(len(names), len(set(names)), "a case was enumerated twice")

    def test_each_shipped_solution_yields_exactly_one_case(self) -> None:
        """A solution directory's history and weeks must be read, not assumed."""
        for solution_dir in self.solution_dirs:
            match = re.match(
                r"^Solution_H_(?P<history>\d+)-WD_(?P<weeks>[\d-]+)$",
                solution_dir.name,
            )
            family = solution_dir.parent.name
            same = [
                case
                for case in self.cases
                if case["name"].startswith(f"{family}_H{match.group('history')}_WD")
                and case["name"].endswith(match.group("weeks"))
            ]
            with self.subTest(instance=solution_dir.name):
                self.assertEqual(len(same), 1)


if __name__ == "__main__":
    unittest.main()
