#!/usr/bin/env python3.14
"""Regression tests for solver output-completeness boundaries."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from cvrp_bench.solver.solverforge_py import _complete_routes
from employee_scheduling_bench.solver.solverforge_py import (
    _ensure_required_shift_assignments,
)
from job_shop_bench.solver.solverforge_py import _scheduled_operations
from solverforge_bench.model import NoSolutionFoundError


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


if __name__ == "__main__":
    unittest.main()
