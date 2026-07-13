#!/usr/bin/env python3.14
"""Regression tests for solverforge-py guardrail integrity."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import verify_solverforge_py_guardrails as guardrails
from solverforge_bench.postgres import make_postgres_config
from solverforge_bench.redaction import (
    REDACTED_VALUE,
    redact_sensitive_command_args,
)


class CommandRedactionTests(unittest.TestCase):
    def test_sensitive_option_forms_are_redacted(self) -> None:
        secret = "postgresql://bench:secret@db.example/bench?sslmode=require"
        command = [
            "python",
            "benchmark.py",
            "--postgres-url",
            secret,
            f"--database-url={secret}",
            "--output",
            "results.csv",
        ]

        redacted = redact_sensitive_command_args(command)

        self.assertNotIn(secret, " ".join(redacted))
        self.assertEqual(redacted[3], REDACTED_VALUE)
        self.assertEqual(redacted[4], f"--database-url={REDACTED_VALUE}")
        self.assertEqual(command[3], secret, "redaction must not mutate execution args")

    def test_successful_run_executes_real_url_but_records_only_redacted_url(
        self,
    ) -> None:
        secret = "postgresql://bench:secret@db.example/bench"
        with tempfile.TemporaryDirectory() as temp_dir:
            args = argparse.Namespace(
                output_dir=Path(temp_dir),
                save_postgres=True,
                database_url=secret,
            )
            records: list[guardrails.RunRecord] = []
            with patch.object(guardrails.subprocess, "run") as run:
                guardrails.run_benchmark(
                    args,
                    phase="comparison",
                    benchmark="cvrp",
                    label="test comparison",
                    output_name="comparison.csv",
                    benchmark_args=["cvrp"],
                    run_records=records,
                )
            summary_path = Path(temp_dir) / "summary.json"
            guardrails.write_summary(
                summary_path, {"runs": [asdict(record) for record in records]}
            )
            serialized_summary = summary_path.read_text(encoding="utf-8")

        executed_command = run.call_args.args[0]
        self.assertIn(secret, executed_command)
        self.assertEqual(len(records), 1)
        self.assertNotIn(secret, serialized_summary)
        self.assertIn(REDACTED_VALUE, serialized_summary)

    def test_failed_run_reports_only_redacted_url(self) -> None:
        secret = "postgresql://bench:secret@db.example/bench"
        with tempfile.TemporaryDirectory() as temp_dir:
            args = argparse.Namespace(
                output_dir=Path(temp_dir),
                save_postgres=True,
                database_url=secret,
            )
            with patch.object(
                guardrails.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(7, ["benchmark"]),
            ):
                with self.assertRaises(guardrails.BenchmarkCommandError) as caught:
                    guardrails.run_benchmark(
                        args,
                        phase="comparison",
                        benchmark="cvrp",
                        label="test comparison",
                        output_name="comparison.csv",
                        benchmark_args=["cvrp"],
                        run_records=[],
                    )

        message = str(caught.exception)
        self.assertNotIn(secret, message)
        self.assertIn(REDACTED_VALUE, message)

    def test_postgres_config_keeps_connection_url_but_redacts_run_metadata(
        self,
    ) -> None:
        secret = "postgresql://bench:secret@db.example/bench"
        args = argparse.Namespace(
            postgres_url=secret,
            run_kind="candidate",
            nightly=False,
            release_tag=None,
            run_stamp="test",
            log_path=None,
            argv=["cvrp", "--postgres-url", secret],
            repo_root=guardrails.REPO_ROOT,
            config=None,
        )
        spec = argparse.Namespace(name="cvrp", category="list_variable")

        config = make_postgres_config(
            args=args,
            spec=spec,
            output_path=Path("results.csv"),
            artifact_dir=Path("artifacts"),
            solvers=[],
            solver_versions={},
            time_limits=[1],
        )

        self.assertEqual(config.database_url, secret)
        self.assertNotIn(secret, json.dumps(config.command_args))
        self.assertIn(REDACTED_VALUE, config.command_args)


class MatrixCoverageTests(unittest.TestCase):
    expectation = guardrails.MatrixExpectation(
        benchmark_name="job-shop-scheduling",
        instances=("ft06", "la01"),
        solvers=("solverforge", "solverforge-py"),
        time_limits=(1, 10),
        requested_dataset_selectors=("ft06", "la01"),
    )

    def test_complete_cartesian_matrix_passes(self) -> None:
        rows = self._rows()

        coverage, failures = guardrails.validate_matrix_coverage(
            rows, "JSSP comparison", self.expectation
        )

        self.assertEqual(failures, [])
        self.assertTrue(coverage["complete"])
        self.assertEqual(coverage["expected_row_count"], 8)

    def test_missing_entire_requested_case_and_time_fails(self) -> None:
        rows = [
            row
            for row in self._rows()
            if not (row["instance"] == "la01" and row["time_limit_seconds"] == "10")
        ]

        coverage, failures = guardrails.validate_matrix_coverage(
            rows, "JSSP comparison", self.expectation
        )

        self.assertFalse(coverage["complete"])
        self.assertEqual(len(coverage["missing_row_keys"]), 2)
        self.assertTrue(
            any("missing requested matrix rows" in item for item in failures)
        )

    def test_duplicate_and_unexpected_rows_fail(self) -> None:
        rows = self._rows()
        rows.append(dict(rows[0]))
        unexpected = dict(rows[0])
        unexpected["instance"] = "not-requested"
        rows.append(unexpected)

        coverage, failures = guardrails.validate_matrix_coverage(
            rows, "JSSP comparison", self.expectation
        )

        self.assertFalse(coverage["complete"])
        self.assertEqual(len(coverage["duplicate_row_keys"]), 1)
        self.assertEqual(len(coverage["unexpected_row_keys"]), 1)
        self.assertEqual(len(failures), 2)

    def test_misspelled_dataset_selectors_fail_preflight(self) -> None:
        with self.assertRaisesRegex(guardrails.GuardrailInputError, "do not exist"):
            guardrails.resolve_jssp_instances(("ft06", "ftO6"))
        with self.assertRaisesRegex(
            guardrails.GuardrailInputError, "matched no instances"
        ):
            guardrails.resolve_employee_instances(("n005w4", "nOO5w4"))

    def _rows(self) -> list[dict[str, str]]:
        return [
            {
                "benchmark_name": self.expectation.benchmark_name,
                "instance": instance,
                "solver": solver,
                "time_limit_seconds": str(time_limit),
            }
            for instance in self.expectation.instances
            for solver in self.expectation.solvers
            for time_limit in self.expectation.time_limits
        ]


if __name__ == "__main__":
    unittest.main()
