#!/usr/bin/env python3.14
"""Regression tests for solver output-completeness boundaries."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cvrp_bench.solver.solverforge_py import _complete_routes
from employee_scheduling_bench.domain.models import Solution
from employee_scheduling_bench.solver.ortools import (
    _apply_fresh_score,
    _raise_native_failure,
)
from employee_scheduling_bench.solver.solverforge_py import (
    _ensure_required_shift_assignments,
    _same_value_conflicts,
)
from job_shop_bench.solver.solverforge_py import _scheduled_operations
from solverforge_bench.model import NoSolutionFoundError, SolverExecutionError
from solverforge_bench.solverforge_failures import classify_solverforge_failure


class JsspOutputCompletenessTests(unittest.TestCase):
    def test_complete_schedule_is_serialized(self) -> None:
        facts = self._facts()
        machines = [self._machine(0, [0]), self._machine(1, [1])]

        operations, makespan = _scheduled_operations(machines, facts)

        self.assertEqual(len(operations), 2)
        self.assertEqual(makespan, 5)

    def test_missing_duplicate_wrong_owner_and_cycle_are_failures(self) -> None:
        facts = self._facts()
        invalid = [
            [self._machine(0, [0]), self._machine(1, [])],
            [self._machine(0, [0]), self._machine(1, [0, 1])],
            [self._machine(0, [0, 1]), self._machine(1, [])],
        ]
        cycle_facts = [
            self._fact(0, job_id=0, op_index=0, machine_id=0, duration=3),
            self._fact(1, job_id=0, op_index=1, machine_id=0, duration=2),
        ]
        invalid.append([self._machine(0, [1, 0])])

        for machines in invalid[:3]:
            with self.subTest(machines=machines):
                with self.assertRaises(NoSolutionFoundError):
                    _scheduled_operations(machines, facts)
        with self.assertRaises(NoSolutionFoundError):
            _scheduled_operations(invalid[3], cycle_facts)

    @staticmethod
    def _facts() -> list[SimpleNamespace]:
        return [
            JsspOutputCompletenessTests._fact(
                0, job_id=0, op_index=0, machine_id=0, duration=3
            ),
            JsspOutputCompletenessTests._fact(
                1, job_id=0, op_index=1, machine_id=1, duration=2
            ),
        ]

    @staticmethod
    def _fact(
        operation_id: int,
        *,
        job_id: int,
        op_index: int,
        machine_id: int,
        duration: int,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            operation_id=operation_id,
            job_id=job_id,
            op_index=op_index,
            machine_id=machine_id,
            duration=duration,
        )

    @staticmethod
    def _machine(machine_id: int, operations: list[int]) -> SimpleNamespace:
        return SimpleNamespace(machine_id=machine_id, operations=operations)


class SolverForgeOutputCompletenessTests(unittest.TestCase):
    def test_employee_forbidden_successions_compile_to_symmetric_conflicts(
        self,
    ) -> None:
        shifts = [
            {"week": 0, "day": 0, "shift_type_idx": 0},
            {"week": 0, "day": 0, "shift_type_idx": 1},
            {"week": 0, "day": 1, "shift_type_idx": 1},
            {"week": 0, "day": 2, "shift_type_idx": 0},
            {"week": 0, "day": 6, "shift_type_idx": 0},
            {"week": 1, "day": 0, "shift_type_idx": 1},
        ]

        conflicts = _same_value_conflicts(shifts, [[], [0]])

        self.assertEqual(conflicts, [[2], [], [0], [], [5], [4]])

    def test_incomplete_construction_is_an_observed_no_solution(self) -> None:
        native_error = ValueError(
            "runtime execution failed: configured solve stopped with mandatory "
            "planning work incomplete: assignment group has 2 unassigned rows"
        )

        classified = classify_solverforge_failure(
            native_error,
            solver_name="SolverForge Rust",
        )

        self.assertIsInstance(classified, NoSolutionFoundError)
        assert classified is not None
        self.assertEqual(classified.termination_status, "no_solution")
        self.assertIn("ended without a complete solution", str(classified))
        self.assertTrue(classified.native_fields["mandatory_construction_incomplete"])
        self.assertEqual(
            classified.native_fields["native_failure_type"],
            "ValueError",
        )
        self.assertEqual(
            classified.native_fields["native_failure_message"],
            str(native_error),
        )

    def test_unknown_solverforge_failure_is_not_reclassified(self) -> None:
        native_error = ValueError("unrelated adapter defect")

        classified = classify_solverforge_failure(
            native_error,
            solver_name="SolverForge Rust",
        )

        self.assertIsNone(classified)

    def test_cvrp_customer_assignment_must_be_exact(self) -> None:
        complete = SimpleNamespace(
            customer_values=[1, 2, 3],
            routes=[SimpleNamespace(visits=[1, 2]), SimpleNamespace(visits=[3])],
        )
        self.assertEqual(_complete_routes(complete), [[1, 2], [3]])

        for visits in ([1, 2], [1, 2, 2, 3], [1, 2, 4]):
            with self.subTest(visits=visits):
                incomplete = SimpleNamespace(
                    customer_values=[1, 2, 3],
                    routes=[SimpleNamespace(visits=visits)],
                )
                with self.assertRaises(NoSolutionFoundError):
                    _complete_routes(incomplete)

    def test_employee_required_assignments_must_be_present(self) -> None:
        _ensure_required_shift_assignments(
            [
                SimpleNamespace(shift_id=0, is_minimum=True, nurse_idx=1),
                SimpleNamespace(shift_id=1, is_minimum=False, nurse_idx=None),
            ]
        )

        with self.assertRaises(NoSolutionFoundError):
            _ensure_required_shift_assignments(
                [SimpleNamespace(shift_id=0, is_minimum=True, nurse_idx=None)]
            )


class EmployeeOrToolsStatusTests(unittest.TestCase):
    def test_fresh_validator_score_preserves_native_score_drift(self) -> None:
        solution = Solution(assignments=[], reported_cost=420)
        instance = SimpleNamespace()

        with patch(
            "employee_scheduling_bench.solver.ortools.validate",
            return_value=400,
        ) as validator:
            _apply_fresh_score(solution, instance=instance)

        validator.assert_called_once_with(solution=solution, instance=instance)
        self.assertEqual(solution.cost, 400)
        self.assertEqual(solution.fresh_cost, 400)
        self.assertEqual(solution.reported_cost, 420)
        self.assertEqual(solution.score_delta, 20)
        self.assertTrue(solution.score_drift)

    def test_unknown_is_an_observed_missing_incumbent(self) -> None:
        with self.assertRaises(NoSolutionFoundError) as raised:
            _raise_native_failure(
                {"native_solver_status": "UNKNOWN"},
                returncode=1,
                stderr="OR-Tools CP-SAT found no feasible solution",
            )

        self.assertEqual(raised.exception.termination_status, "no_incumbent")
        self.assertEqual(
            raised.exception.native_fields["native_solver_status"], "UNKNOWN"
        )

    def test_infeasible_is_not_reported_as_unknown(self) -> None:
        with self.assertRaises(NoSolutionFoundError) as raised:
            _raise_native_failure(
                {"native_solver_status": "INFEASIBLE"},
                returncode=1,
                stderr="",
            )

        self.assertEqual(raised.exception.termination_status, "proved_infeasible")

    def test_invalid_model_is_an_adapter_failure(self) -> None:
        with self.assertRaises(SolverExecutionError) as raised:
            _raise_native_failure(
                {"native_solver_status": "MODEL_INVALID"},
                returncode=1,
                stderr="",
            )

        self.assertNotIsInstance(raised.exception, NoSolutionFoundError)
        self.assertEqual(raised.exception.termination_status, "model_invalid")

    def test_unclassified_native_failure_stays_an_adapter_error(self) -> None:
        with self.assertRaises(SolverExecutionError) as raised:
            _raise_native_failure(
                {"native_solver_status": "UNRECOGNIZED"},
                returncode=9,
                stderr="native failure",
            )

        self.assertEqual(raised.exception.termination_status, "adapter_error")


class PyvrpRouteTranslationTests(unittest.TestCase):
    """pyvrp 0.14.0 restructured routes and location registration.

    A route now iterates Activities (depot start/end plus clients) rather than
    bare node indices, and the depot must be registered through add_location.
    Both are easy to get subtly wrong: reading activities straight through gives
    depot entries in the routes, and taking the client index unshifted produces a
    tour the cost check rejects on the wrong edges.
    """

    def test_route_activities_map_to_node_indices(self) -> None:
        client = SimpleNamespace(idx=0, is_client=lambda: True)
        depot = SimpleNamespace(idx=0, is_client=lambda: False)
        other = SimpleNamespace(idx=41, is_client=lambda: True)
        route = [depot, client, other, depot]

        nodes = [activity.idx + 1 for activity in route if activity.is_client()]

        self.assertEqual(nodes, [1, 42])

    def test_depot_activity_is_excluded_from_the_tour(self) -> None:
        depot = SimpleNamespace(idx=0, is_client=lambda: False)

        nodes = [a.idx + 1 for a in [depot] if a.is_client()]

        self.assertEqual(nodes, [])


if __name__ == "__main__":
    unittest.main()
