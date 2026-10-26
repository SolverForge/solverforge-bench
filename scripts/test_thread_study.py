"""Thread-study variant registry and report contracts."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from cvrp_bench.solver.solver import AVAILABLE_METHODS as CVRP_AVAILABLE
from cvrp_bench.solver.solver import DEFAULT_METHODS as CVRP_DEFAULTS
from employee_scheduling_bench.solver.solver import (
    AVAILABLE_METHODS as EMPLOYEE_AVAILABLE,
)
from employee_scheduling_bench.solver.solver import (
    DEFAULT_METHODS as EMPLOYEE_DEFAULTS,
)
from solverforge_bench.thread_study import (
    StudyRun,
    read_study_runs,
    render_report,
    thread_variant_count,
    thread_variant_methods,
    verdict,
)


def _run(threads: int, cost: float, *, feasible: bool = True) -> StudyRun:
    return StudyRun(
        benchmark="cvrp",
        instance="X-n101-k25",
        time_limit=10,
        threads=threads,
        feasible=feasible,
        cost=cost,
        moves_evaluated=1000 * threads,
        moves_speculative=100 * (threads - 1),
        step_count=100,
        elapsed_ms=10_000,
    )


class ThreadStudyTests(unittest.TestCase):
    def test_variants_are_registered_but_never_default(self) -> None:
        for available, defaults in (
            (CVRP_AVAILABLE, CVRP_DEFAULTS),
            (EMPLOYEE_AVAILABLE, EMPLOYEE_DEFAULTS),
        ):
            for variant in thread_variant_methods():
                self.assertIn(variant, available)
                self.assertNotIn(variant, defaults)

    def test_variant_names_parse_to_their_thread_count(self) -> None:
        self.assertEqual(thread_variant_count("solverforge-t4"), 4)
        self.assertIsNone(thread_variant_count("solverforge"))
        self.assertIsNone(thread_variant_count("solverforge-t3"))
        self.assertIsNone(thread_variant_count("solverforge-py"))

    def test_verdict_prefers_feasibility_then_cost_outside_the_tie_band(self) -> None:
        self.assertEqual(verdict(_run(1, 1000), _run(4, 900)), "4 threads")
        self.assertEqual(verdict(_run(1, 1000), _run(4, 1100)), "1 thread")
        self.assertEqual(verdict(_run(1, 1000), _run(4, 1003)), "tie")
        self.assertEqual(
            verdict(_run(1, 1000), _run(4, 900, feasible=False)), "1 thread"
        )

    def test_report_reads_native_telemetry_from_result_csvs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "benchmark_name",
                        "instance",
                        "solver",
                        "time_limit_seconds",
                        "hard_feasible",
                        "cost",
                        "solver_metadata",
                    ],
                )
                writer.writeheader()
                for solver, cost, evaluated, speculative in (
                    ("solverforge", 1000, 50_000, 0),
                    ("solverforge-t4", 950, 120_000, 40_000),
                    ("timefold", 900, 0, 0),
                ):
                    writer.writerow(
                        {
                            "benchmark_name": "cvrp",
                            "instance": "X-n101-k25",
                            "solver": solver,
                            "time_limit_seconds": 10,
                            "hard_feasible": "true",
                            "cost": cost,
                            "solver_metadata": json.dumps(
                                {
                                    "solverforge_telemetry": {
                                        "moves_evaluated": evaluated,
                                        "moves_speculative": speculative,
                                        "step_count": 1000,
                                        "elapsed_ms": 10_000,
                                    }
                                }
                            ),
                        }
                    )

            runs = read_study_runs([path])
            report = render_report(runs)

        self.assertEqual(sorted(run.threads for run in runs), [1, 4])
        self.assertIn(
            "| X-n101-k25 | 10s | 4 | 950 | -5.0% | 2.40x | 25% | 120 | 4 threads |",
            report,
        )


if __name__ == "__main__":
    unittest.main()
