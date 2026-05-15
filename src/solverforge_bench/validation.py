"""Shared validation helpers for benchmark run contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from solverforge_bench.model import SolverVersion


def duplicate_values(values: Iterable[str]) -> list[str]:
    seen = set()
    duplicates = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def validate_unique_solvers(solvers: Iterable[str]) -> list[str]:
    solver_list = list(solvers)
    duplicates = duplicate_values(solver_list)
    if duplicates:
        raise ValueError(
            f"Duplicate solver(s) are not allowed: {', '.join(duplicates)}"
        )
    return solver_list


def validate_solver_versions(
    solvers: Iterable[str],
    solver_versions: Mapping[str, SolverVersion],
) -> None:
    missing = [solver for solver in solvers if solver not in solver_versions]
    if missing:
        raise ValueError(
            "Missing solver version metadata for solver(s): " f"{', '.join(missing)}"
        )

    mismatched = [
        f"{solver}={solver_versions[solver].solver}"
        for solver in solvers
        if solver_versions[solver].solver != solver
    ]
    if mismatched:
        raise ValueError(
            "Solver version metadata uses mismatched solver name(s): "
            f"{', '.join(mismatched)}"
        )
