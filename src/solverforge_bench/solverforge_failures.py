"""Shared classification for SolverForge solve-boundary failures."""

from __future__ import annotations

from solverforge_bench.model import NoSolutionFoundError


MANDATORY_CONSTRUCTION_INCOMPLETE_MARKER = (
    "configured solve stopped with mandatory planning work incomplete:"
)


def classify_solverforge_failure(
    error: Exception,
    *,
    solver_name: str,
) -> NoSolutionFoundError | None:
    """Return an honest no-solution outcome for a known construction stop."""

    failure_message = str(error)
    if MANDATORY_CONSTRUCTION_INCOMPLETE_MARKER not in failure_message:
        return None

    return NoSolutionFoundError(
        f"{solver_name} ended without a complete solution at the configured "
        f"time limit: {failure_message}",
        native_fields={
            "mandatory_construction_incomplete": True,
            "native_failure_type": error.__class__.__name__,
            "native_failure_message": failure_message,
        },
    )
