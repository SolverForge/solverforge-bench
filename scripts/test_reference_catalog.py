#!/usr/bin/env python3.14
"""Regression tests for the shared reference catalog.

The catalog is the only thing standing between a published mean gap and a
number graded against nothing, so its failure modes get tests: a missing
catalog, a malformed entry, an instance with no reference, and a reference kind
that does not describe what was actually proven.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from solverforge_bench.references import (
    BEST_KNOWN_UPPER_BOUND,
    CATALOG_FILE,
    KNOWN_OPTIMUM,
    ReferenceCatalogError,
    catalog_instances,
    load_catalog,
    reference_for,
    references_by_instance,
)

SOURCE = {"name": "Example benchmark corpus", "revision": "abc123"}


def write_catalog(
    directory: Path, instances: dict, source: dict | None = SOURCE
) -> None:
    payload = {"instances": instances}
    if source is not None:
        payload["source"] = source
    (directory / CATALOG_FILE).write_text(json.dumps(payload))


class ReferenceCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_closed_instance_resolves_as_known_optimum(self) -> None:
        write_catalog(self.data, {"a1": {"reference": 100, "status": "closed"}})
        reference = reference_for(self.data, "a1")
        self.assertEqual(reference.reference_cost, 100.0)
        self.assertEqual(reference.kind, KNOWN_OPTIMUM)
        self.assertTrue(reference.is_optimum)
        self.assertEqual(reference.source_name, SOURCE["name"])
        self.assertEqual(reference.source_revision, SOURCE["revision"])

    def test_open_instance_resolves_as_best_known_upper_bound(self) -> None:
        write_catalog(
            self.data,
            {"a1": {"reference": 100, "status": "open", "lower_bound": 90}},
        )
        reference = reference_for(self.data, "a1")
        self.assertEqual(reference.kind, BEST_KNOWN_UPPER_BOUND)
        self.assertFalse(reference.is_optimum)
        self.assertEqual(reference.lower_bound, 90.0)

    def test_reference_kind_is_derived_from_status_not_from_bounds(self) -> None:
        """An open instance whose bounds happen to meet is still not a proof."""
        write_catalog(
            self.data,
            {"a1": {"reference": 100, "status": "open", "lower_bound": 100}},
        )
        self.assertEqual(reference_for(self.data, "a1").kind, BEST_KNOWN_UPPER_BOUND)

    def test_gap_and_ratio_are_relative_to_the_reference(self) -> None:
        write_catalog(self.data, {"a1": {"reference": 100, "status": "closed"}})
        reference = reference_for(self.data, "a1")
        self.assertAlmostEqual(reference.gap(110), 0.1)
        self.assertAlmostEqual(reference.ratio(110), 1.1)
        self.assertAlmostEqual(reference.gap(100), 0.0)

    def test_missing_instance_raises_instead_of_returning_none(self) -> None:
        write_catalog(self.data, {"a1": {"reference": 100, "status": "closed"}})
        with self.assertRaises(ReferenceCatalogError):
            reference_for(self.data, "a2")

    def test_missing_catalog_raises(self) -> None:
        with self.assertRaises(ReferenceCatalogError):
            reference_for(self.data, "a1")

    def test_catalog_without_source_raises(self) -> None:
        """A reference nobody can trace is not publishable."""
        write_catalog(
            self.data, {"a1": {"reference": 100, "status": "closed"}}, source=None
        )
        with self.assertRaises(ReferenceCatalogError):
            load_catalog(str(self.data))

    def test_catalog_with_blank_source_revision_raises(self) -> None:
        write_catalog(
            self.data,
            {"a1": {"reference": 100, "status": "closed"}},
            source={"name": "Example", "revision": "  "},
        )
        with self.assertRaises(ReferenceCatalogError):
            load_catalog(str(self.data))

    def test_unknown_status_raises(self) -> None:
        write_catalog(self.data, {"a1": {"reference": 100, "status": "probably"}})
        with self.assertRaises(ReferenceCatalogError):
            load_catalog(str(self.data))

    def test_non_positive_reference_raises(self) -> None:
        for bad in (0, -5, None, "100"):
            with self.subTest(reference=bad):
                write_catalog(self.data, {"a1": {"reference": bad, "status": "closed"}})
                with self.assertRaises(ReferenceCatalogError):
                    load_catalog(str(self.data))

    def test_empty_catalog_raises(self) -> None:
        write_catalog(self.data, {})
        with self.assertRaises(ReferenceCatalogError):
            load_catalog(str(self.data))

    def test_boolean_reference_is_rejected(self) -> None:
        """True is an int in Python and must not pass as a cost of 1."""
        write_catalog(self.data, {"a1": {"reference": True, "status": "closed"}})
        with self.assertRaises(ReferenceCatalogError):
            load_catalog(str(self.data))

    def test_catalog_instances_lists_exactly_the_covered_names(self) -> None:
        write_catalog(
            self.data,
            {
                "a1": {"reference": 100, "status": "closed"},
                "a2": {"reference": 200, "status": "open"},
            },
        )
        self.assertEqual(catalog_instances(self.data), frozenset({"a1", "a2"}))

    def test_batch_resolution_covers_every_requested_instance(self) -> None:
        write_catalog(
            self.data,
            {
                "a1": {"reference": 100, "status": "closed"},
                "a2": {"reference": 200, "status": "open"},
            },
        )
        resolved = references_by_instance(self.data, ["a1", "a2"])
        self.assertEqual(set(resolved), {"a1", "a2"})

    def test_batch_resolution_fails_on_a_gap(self) -> None:
        write_catalog(self.data, {"a1": {"reference": 100, "status": "closed"}})
        with self.assertRaises(ReferenceCatalogError):
            references_by_instance(self.data, ["a1", "missing"])

    def test_native_fields_travel_with_the_reference(self) -> None:
        write_catalog(
            self.data,
            {
                "a1": {
                    "reference": 100,
                    "status": "closed",
                    "native_fields": {"family": "example"},
                }
            },
        )
        self.assertEqual(
            reference_for(self.data, "a1").native_fields, {"family": "example"}
        )

    def test_missing_native_fields_is_not_an_error(self) -> None:
        write_catalog(self.data, {"a1": {"reference": 100, "status": "closed"}})
        self.assertEqual(reference_for(self.data, "a1").native_fields, {})


if __name__ == "__main__":
    unittest.main()
