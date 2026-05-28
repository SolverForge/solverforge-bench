"""Runtime fair-start witness helpers."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from contextvars import ContextVar
from contextlib import contextmanager
from collections.abc import Callable, Iterator
from typing import Any

from solverforge_bench.model import FairStartWitness, SolverResult


FAIR_START_WITNESS_VERSION = 1
_WITNESS_RECORDER: ContextVar[Callable[[FairStartWitness], None] | None] = ContextVar(
    "fair_start_witness_recorder", default=None
)
_PRECOMPUTED_INPUT_HASH: ContextVar[str | None] = ContextVar(
    "fair_start_precomputed_input_hash", default=None
)


class FairStartViolationError(RuntimeError):
    """Raised when a solver run lacks a valid fair-start witness."""


def make_fair_start_witness(
    *,
    benchmark_name: str,
    solver: str,
    planning_state: str,
    solver_input: Any,
    solver_input_hash: str | None = None,
    reference_solution_reads: int = 0,
    adapter_hint_count: int = 0,
    preliminary_solve_count: int = 0,
    fallback_solution_enabled: bool = False,
    preassigned_scalar_variables: int = 0,
    prefilled_list_variables: int = 0,
    native_checks: dict[str, Any] | None = None,
) -> FairStartWitness:
    return FairStartWitness(
        version=FAIR_START_WITNESS_VERSION,
        benchmark_name=benchmark_name,
        solver=solver,
        planning_state=planning_state,
        solver_input_hash=_solver_input_hash(
            solver_input=solver_input,
            explicit_hash=solver_input_hash,
        ),
        reference_solution_reads=reference_solution_reads,
        adapter_hint_count=adapter_hint_count,
        preliminary_solve_count=preliminary_solve_count,
        fallback_solution_enabled=fallback_solution_enabled,
        preassigned_scalar_variables=preassigned_scalar_variables,
        prefilled_list_variables=prefilled_list_variables,
        native_checks=dict(native_checks or {}),
    )


def solver_result(solution: Any, witness: FairStartWitness) -> SolverResult:
    return SolverResult(solution=solution, fair_start_witness=witness)


def emit_fair_start_witness(witness: FairStartWitness) -> None:
    recorder = _WITNESS_RECORDER.get()
    if recorder is not None:
        recorder(witness)


@contextmanager
def fair_start_input_hash(solver_input_hash: str | None) -> Iterator[None]:
    token = _PRECOMPUTED_INPUT_HASH.set(solver_input_hash)
    try:
        yield
    finally:
        _PRECOMPUTED_INPUT_HASH.reset(token)


@contextmanager
def fair_start_recorder(
    recorder: Callable[[FairStartWitness], None],
) -> Iterator[None]:
    token = _WITNESS_RECORDER.set(recorder)
    try:
        yield
    finally:
        _WITNESS_RECORDER.reset(token)


def stable_input_hash(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = json.dumps(
            json_safe(value),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _solver_input_hash(*, solver_input: Any, explicit_hash: str | None) -> str:
    if explicit_hash is not None:
        return _validated_solver_input_hash(explicit_hash)
    precomputed_hash = _PRECOMPUTED_INPUT_HASH.get()
    if precomputed_hash is not None:
        return _validated_solver_input_hash(precomputed_hash)
    return stable_input_hash(solver_input)


def _validated_solver_input_hash(value: str) -> str:
    if not _looks_like_sha256(value):
        raise ValueError(f"solver_input_hash is not a sha256 hex digest: {value!r}")
    return value


def validate_solver_result(
    result: Any, *, benchmark_name: str, solver_name: str
) -> SolverResult:
    if not isinstance(result, SolverResult):
        raise FairStartViolationError(
            f"{solver_name} returned {type(result).__name__}; expected SolverResult"
        )
    validate_fair_start_witness(
        result.fair_start_witness,
        benchmark_name=benchmark_name,
        solver_name=solver_name,
    )
    return result


def validate_fair_start_witness(
    witness: FairStartWitness,
    *,
    benchmark_name: str,
    solver_name: str,
) -> None:
    errors: list[str] = []
    if not isinstance(witness, FairStartWitness):
        raise FairStartViolationError(
            f"{solver_name} returned no FairStartWitness instance"
        )
    if witness.version != FAIR_START_WITNESS_VERSION:
        errors.append(f"version={witness.version}")
    if witness.benchmark_name != benchmark_name:
        errors.append(f"benchmark_name={witness.benchmark_name!r}")
    if witness.solver != solver_name:
        errors.append(f"solver={witness.solver!r}")
    if not witness.planning_state:
        errors.append("planning_state is blank")
    if not _looks_like_sha256(witness.solver_input_hash):
        errors.append("solver_input_hash is not a sha256 hex digest")

    zero_fields = {
        "reference_solution_reads": witness.reference_solution_reads,
        "adapter_hint_count": witness.adapter_hint_count,
        "preliminary_solve_count": witness.preliminary_solve_count,
        "preassigned_scalar_variables": witness.preassigned_scalar_variables,
        "prefilled_list_variables": witness.prefilled_list_variables,
    }
    for field_name, value in zero_fields.items():
        if value != 0:
            errors.append(f"{field_name}={value}")
    if witness.fallback_solution_enabled:
        errors.append("fallback_solution_enabled=true")
    for field_name in ("cp_sat_solution_hint_vars", "cp_sat_solution_hint_values"):
        value = witness.native_checks.get(field_name)
        if value not in (None, 0):
            errors.append(f"{field_name}={value}")
    if witness.native_checks.get("routing_assignment_hint_present") is True:
        errors.append("routing_assignment_hint_present=true")

    if errors:
        raise FairStartViolationError(
            f"{solver_name} fair-start witness failed: {', '.join(errors)}"
        )


def witness_to_payload(witness: FairStartWitness) -> dict[str, Any]:
    return json_safe(witness.as_dict())


def witness_from_payload(payload: dict[str, Any] | None) -> FairStartWitness | None:
    if payload is None:
        return None
    return FairStartWitness(**payload)


def witness_from_native_output(
    output: dict[str, Any],
    *,
    benchmark_name: str,
    solver: str,
    planning_state: str,
    solver_input: Any,
    witness_key: str = "fair_start_witness",
) -> FairStartWitness:
    native_witness = output.get(witness_key)
    if native_witness is None:
        raise FairStartViolationError(
            f"{solver} native output did not include {witness_key!r}"
        )
    if not isinstance(native_witness, dict):
        raise FairStartViolationError(
            f"{solver} native {witness_key!r} must be an object"
        )
    native_checks = dict(native_witness)
    return make_fair_start_witness(
        benchmark_name=benchmark_name,
        solver=solver,
        planning_state=planning_state,
        solver_input=solver_input,
        reference_solution_reads=int(native_checks.pop("reference_solution_reads", 0)),
        adapter_hint_count=int(native_checks.pop("adapter_hint_count", 0)),
        preliminary_solve_count=int(native_checks.pop("preliminary_solve_count", 0)),
        fallback_solution_enabled=bool(
            native_checks.pop("fallback_solution_enabled", False)
        ),
        preassigned_scalar_variables=int(
            native_checks.pop("preassigned_scalar_variables", 0)
        ),
        prefilled_list_variables=int(native_checks.pop("prefilled_list_variables", 0)),
        native_checks=native_checks,
    )


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    if hasattr(value, "model_dump"):
        return json_safe(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    return str(value)


def _looks_like_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(char in "0123456789abcdef" for char in value)
