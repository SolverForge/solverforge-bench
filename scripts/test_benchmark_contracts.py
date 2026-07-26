#!/usr/bin/env python3.14
"""Regression tests for shared benchmark publication contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from solverforge_bench.matrix import BenchmarkMatrix, BenchmarkMatrixTracker
from solverforge_bench.model import (
    BenchmarkCase,
    SolverVersion,
)
from solverforge_bench.solver_versions import (
    cargo_dependency_version,
    executable_version,
)
from solverforge_bench.validation import validate_solver_versions


class BenchmarkMatrixTests(unittest.TestCase):
    def test_complete_matrix_has_stable_hash(self) -> None:
        matrix = self._matrix()
        reordered = BenchmarkMatrix.build(
            benchmark_name="test",
            cases=reversed(matrix.cases),
            solvers=reversed(matrix.solvers),
            time_limits_seconds=reversed(matrix.time_limits_seconds),
        )
        tracker = BenchmarkMatrixTracker(matrix)
        for key in reversed(matrix.expected_keys):
            tracker.mark_observed(key)

        tracker.assert_complete()
        self.assertEqual(matrix.expected_count, 8)
        self.assertEqual(matrix.sha256, reordered.sha256)
        self.assertEqual(matrix.sha256, tracker.observed_sha256)

    def test_missing_duplicate_and_unexpected_rows_fail(self) -> None:
        matrix = self._matrix()
        tracker = BenchmarkMatrixTracker(matrix)
        tracker.mark_observed(matrix.expected_keys[0])

        with self.assertRaisesRegex(ValueError, "Duplicate benchmark matrix row"):
            tracker.mark_observed(matrix.expected_keys[0])
        with self.assertRaisesRegex(ValueError, "Unexpected benchmark matrix row"):
            tracker.mark_observed(
                matrix.expected_keys[0].__class__(
                    benchmark_name="test",
                    dataset="dataset",
                    dataset_set="canonical",
                    instance="not-requested",
                    solver="solver-a",
                    time_limit_seconds=1,
                )
            )
        with self.assertRaisesRegex(ValueError, "matrix is incomplete"):
            tracker.assert_complete()

    def test_empty_duplicate_and_nonpositive_inputs_fail_preflight(self) -> None:
        with self.assertRaisesRegex(ValueError, "selected no cases"):
            BenchmarkMatrix.build(
                benchmark_name="test",
                cases=[],
                solvers=["solver-a"],
                time_limits_seconds=[1],
            )
        with self.assertRaisesRegex(ValueError, "selected no time limits"):
            BenchmarkMatrix.build(
                benchmark_name="test",
                cases=[self._case("one")],
                solvers=["solver-a"],
                time_limits_seconds=[],
            )
        with self.assertRaisesRegex(ValueError, "Duplicate benchmark case"):
            BenchmarkMatrix.build(
                benchmark_name="test",
                cases=[self._case("one"), self._case("one")],
                solvers=["solver-a"],
                time_limits_seconds=[1],
            )
        with self.assertRaisesRegex(ValueError, "positive integer"):
            BenchmarkMatrix.build(
                benchmark_name="test",
                cases=[self._case("one")],
                solvers=["solver-a"],
                time_limits_seconds=[0],
            )

    def _matrix(self) -> BenchmarkMatrix:
        return BenchmarkMatrix.build(
            benchmark_name="test",
            cases=[self._case("one"), self._case("two")],
            solvers=["solver-a", "solver-b"],
            time_limits_seconds=[1, 10],
        )

    @staticmethod
    def _case(instance: str) -> BenchmarkCase:
        return BenchmarkCase(
            dataset="dataset",
            dataset_set="canonical",
            instance=instance,
            instance_size=1,
            payload={"instance": instance},
        )


class SolverProvenanceTests(unittest.TestCase):
    def test_cargo_runtime_provenance_uses_lock_and_binary_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cargo_toml = root / "Cargo.toml"
            cargo_toml.write_text(
                """
[package]
name = "adapter"
version = "0.1.0"

[dependencies]
solverforge = "0.19.2"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "Cargo.lock").write_text(
                """
version = 4

[[package]]
name = "solverforge"
version = "0.19.2"
source = "registry+https://github.com/rust-lang/crates.io-index"
checksum = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            binary = root / "adapter.so"
            binary.write_bytes(b"native runtime")

            version = cargo_dependency_version(
                cargo_toml,
                "solverforge",
                runtime_paths=[binary],
            )("solverforge")

        validate_solver_versions(["solverforge"], {"solverforge": version})
        self.assertEqual(version.version, "0.19.2")
        self.assertEqual(version.metadata["cargo_dependency"]["checksum"], "a" * 64)
        self.assertEqual(
            version.metadata["runtime_artifacts"][0]["kind"], "native_binary"
        )

    def test_executable_provenance_hashes_the_invoked_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "solver"
            executable.write_text(
                "#!/bin/sh\nprintf '%s\\n' 'solver 1.2.3'\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)

            version = executable_version(executable)("solver")

        validate_solver_versions(["solver"], {"solver": version})
        self.assertEqual(version.version, "1.2.3")
        self.assertEqual(version.metadata["runtime_artifacts"][0]["kind"], "executable")

    def test_missing_provenance_is_rejected(self) -> None:
        version = SolverVersion(
            solver="solver",
            version="1.0.0",
            source="test",
        )

        with self.assertRaisesRegex(ValueError, "provenance is incomplete"):
            validate_solver_versions(["solver"], {"solver": version})


if __name__ == "__main__":
    unittest.main()
