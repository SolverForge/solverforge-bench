#!/usr/bin/env python3.14
"""Regression tests for the stock SolverForge guardrail row checks."""

from __future__ import annotations

import unittest

import verify_stock_solverforge_guardrails as guardrails


def row(
    solver: str, run_error: str = "", termination_status: str = "solution_returned"
):
    return {
        "instance": "swv20",
        "solver": solver,
        "time_limit_seconds": "1",
        "fair_start_valid": "true",
        "run_error": run_error,
        "termination_status": termination_status,
        "watchdog_killed": "false",
    }


class CommonRowTests(unittest.TestCase):
    def test_reference_without_schedule_is_a_result(self) -> None:
        for solver, status in (("highs", "no_incumbent"), ("timefold", "no_solution")):
            rows = [row(solver, "NoSolutionFoundError: none in time", status)]
            self.assertEqual(guardrails.validate_common_rows(rows, "JSSP"), [], solver)

    def test_reference_crash_still_fails(self) -> None:
        for status in ("adapter_error", "proved_infeasible", "model_invalid"):
            rows = [row("timefold", "RuntimeError: timefold solver failed", status)]
            failures = guardrails.validate_common_rows(rows, "JSSP")
            self.assertEqual(len(failures), 1, status)

    def test_solverforge_without_schedule_still_fails(self) -> None:
        for solver in ("solverforge", "solverforge-py"):
            rows = [row(solver, "NoSolutionFoundError: none in time", "no_solution")]
            failures = guardrails.validate_common_rows(rows, "JSSP")
            self.assertEqual(len(failures), 1, solver)


if __name__ == "__main__":
    unittest.main()
