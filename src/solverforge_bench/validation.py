"""Shared validation helpers for benchmark run contracts."""

from __future__ import annotations

import re
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
    solver_list = list(solvers)
    missing = [solver for solver in solver_list if solver not in solver_versions]
    if missing:
        raise ValueError(
            "Missing solver version metadata for solver(s): " f"{', '.join(missing)}"
        )

    mismatched = [
        f"{solver}={solver_versions[solver].solver}"
        for solver in solver_list
        if solver_versions[solver].solver != solver
    ]
    if mismatched:
        raise ValueError(
            "Solver version metadata uses mismatched solver name(s): "
            f"{', '.join(mismatched)}"
        )

    invalid = []
    for solver in solver_list:
        version = solver_versions[solver]
        errors = _solver_provenance_errors(version)
        if errors:
            invalid.append(f"{solver}: {', '.join(errors)}")
    if invalid:
        raise ValueError(
            "Solver runtime provenance is incomplete: " + "; ".join(invalid)
        )


def _solver_provenance_errors(version: SolverVersion) -> list[str]:
    errors = []
    if not version.version.strip() or version.version == "unknown":
        errors.append("version is unknown")
    if not version.source.strip() or version.source == "unregistered":
        errors.append("version source is unregistered")

    metadata = version.metadata
    if metadata.get("provenance_schema_version") != 1:
        errors.append("provenance schema is missing")
    provenance_sha256 = metadata.get("provenance_sha256")
    if not isinstance(provenance_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", provenance_sha256
    ):
        errors.append("provenance hash is missing")

    artifacts = metadata.get("runtime_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("runtime artifacts are missing")
        return errors
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"runtime artifact {index} is invalid")
            continue
        sha256 = artifact.get("sha256")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            errors.append(f"runtime artifact {index} hash is missing")
        size = artifact.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append(f"runtime artifact {index} size is invalid")
        kind = artifact.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            errors.append(f"runtime artifact {index} kind is missing")
    return errors
