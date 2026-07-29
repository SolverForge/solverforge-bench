#!/usr/bin/env python3.14
"""Tests for the historical publication re-audit."""

from __future__ import annotations

import unittest

from scripts.reaudit_legacy_publication import decision_for_row, fetch_legacy_rows


class LegacyPublicationReauditTests(unittest.TestCase):
    def test_database_transaction_is_forced_read_only(self) -> None:
        class FakeResult:
            def fetchall(self):
                return [{"run_id": "run-old"}]

        class FakeConnection:
            def __init__(self) -> None:
                self.statements: list[str] = []

            def execute(self, statement: str):
                self.statements.append(statement)
                return FakeResult()

        connection = FakeConnection()

        rows = fetch_legacy_rows(connection)

        self.assertEqual([{"run_id": "run-old"}], rows)
        self.assertEqual("SET TRANSACTION READ ONLY", connection.statements[0])
        self.assertTrue(connection.statements[1].lstrip().startswith("SELECT"))

    def test_missing_immutable_evidence_stays_private(self) -> None:
        decision = decision_for_row(
            {
                "run_id": "run-old",
                "benchmark_name": "employee-scheduling",
                "publication_ready": False,
                "publication_failures": [
                    "expected_matrix_missing",
                    "solver_provenance_incomplete",
                ],
                "expected_result_count": None,
                "expected_matrix_sha256": None,
                "expected_catalog_count": 0,
                "solver_provenance_valid": False,
                "all_fair_start_valid": True,
            }
        )

        self.assertEqual(decision["decision"], "retain_private")
        self.assertIn(
            "legacy_predeclared_matrix_evidence_absent",
            decision["reasons"],
        )
        self.assertIn(
            "legacy_runtime_artifact_identity_absent",
            decision["reasons"],
        )

    def test_currently_publishable_run_needs_no_legacy_repair(self) -> None:
        decision = decision_for_row(
            {
                "run_id": "run-new",
                "benchmark_name": "cvrp",
                "publication_ready": True,
                "publication_failures": [],
                "expected_result_count": 10,
                "expected_matrix_sha256": "a" * 64,
                "expected_catalog_count": 10,
                "solver_provenance_valid": True,
                "all_fair_start_valid": True,
            }
        )

        self.assertEqual(decision["decision"], "publishable")
        self.assertEqual(decision["reasons"], [])


if __name__ == "__main__":
    unittest.main()
