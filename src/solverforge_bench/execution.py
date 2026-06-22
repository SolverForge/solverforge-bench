"""Timed solver execution with watchdog-only process containment."""

from __future__ import annotations

import multiprocessing as mp
import os
import queue as queue_module
import signal
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from solverforge_bench.fair_start import (
    FairStartViolationError,
    fair_start_input_hash,
    fair_start_recorder,
    validate_fair_start_witness,
    validate_solver_result,
    witness_from_payload,
    witness_to_payload,
)
from solverforge_bench.logging import capture_output
from solverforge_bench.model import NoSolutionFoundError, SolverRun


def watchdog_limit_seconds(
    time_limit_seconds: int,
    *,
    multiplier: float,
    grace_seconds: float,
) -> float:
    if time_limit_seconds < 1:
        raise ValueError(f"time_limit must be >= 1 second, got {time_limit_seconds}")
    if multiplier < 1.0:
        raise ValueError(f"watchdog multiplier must be >= 1.0, got {multiplier}")
    if grace_seconds < 0:
        raise ValueError(f"watchdog grace must be >= 0 seconds, got {grace_seconds}")
    return max(time_limit_seconds * multiplier, time_limit_seconds + grace_seconds)


def run_solver(
    *,
    benchmark_name: str,
    solver_name: str,
    solver_factory: Callable[..., Callable[[Any, int], Any]],
    solution_model: type,
    instance: Any,
    time_limit_seconds: int,
    watchdog_seconds: float,
    solver_input_hash: str | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    capture_solver_output: bool = True,
    show_solver_output: bool = True,
) -> SolverRun:
    """Pass the benchmark budget to the solver and wait up to watchdog_seconds."""

    ctx = _process_context()
    output_queue = ctx.Queue()
    process = ctx.Process(
        target=_run_solver_child,
        args=(
            benchmark_name,
            solver_name,
            solver_factory,
            instance,
            solver_input_hash,
            time_limit_seconds,
            output_queue,
            str(stdout_path) if stdout_path else None,
            str(stderr_path) if stderr_path else None,
            capture_solver_output,
            show_solver_output,
        ),
    )
    started = time.monotonic()
    process.start()
    deadline = started + watchdog_seconds
    message = None
    fair_start_witness = None
    while process.is_alive() and time.monotonic() < deadline:
        message, fair_start_witness = _collect_child_messages(
            output_queue,
            result_message=message,
            fair_start_witness=fair_start_witness,
            wait_seconds=0.0,
        )
        process.join(min(0.05, max(0.0, deadline - time.monotonic())))
    elapsed = time.monotonic() - started

    if process.is_alive():
        _terminate_process_tree(process)
        elapsed = time.monotonic() - started
        message, fair_start_witness = _collect_child_messages(
            output_queue,
            result_message=message,
            fair_start_witness=fair_start_witness,
        )
        fair_start_error = (
            None
            if fair_start_witness is not None
            else f"{solver_name} emitted no fair-start witness before watchdog kill"
        )
        return SolverRun(
            solver=solver_name,
            time_limit_seconds=time_limit_seconds,
            actual_time_seconds=elapsed,
            watchdog_limit_seconds=watchdog_seconds,
            watchdog_killed=True,
            solution=None,
            fair_start_witness=fair_start_witness,
            fair_start_valid=fair_start_error is None,
            fair_start_error=fair_start_error,
            run_error=(
                f"WatchdogTimeout: {solver_name} exceeded watchdog limit "
                f"({elapsed:.6f}s > {watchdog_seconds:.6f}s)"
            ),
            exit_code=process.exitcode,
            solver_stdout_path=str(stdout_path) if stdout_path else None,
            solver_stderr_path=str(stderr_path) if stderr_path else None,
        )

    message, fair_start_witness = _collect_child_messages(
        output_queue,
        result_message=message,
        fair_start_witness=fair_start_witness,
    )
    if message is None:
        fair_start_error = (
            None
            if fair_start_witness is not None
            else f"{solver_name} emitted no fair-start witness"
        )
        return SolverRun(
            solver=solver_name,
            time_limit_seconds=time_limit_seconds,
            actual_time_seconds=elapsed,
            watchdog_limit_seconds=watchdog_seconds,
            watchdog_killed=False,
            solution=None,
            fair_start_witness=fair_start_witness,
            fair_start_valid=fair_start_error is None,
            fair_start_error=fair_start_error,
            run_error=(
                f"RuntimeError: {solver_name} exited without producing a result "
                f"(exit {process.exitcode})"
            ),
            exit_code=process.exitcode,
            solver_stdout_path=str(stdout_path) if stdout_path else None,
            solver_stderr_path=str(stderr_path) if stderr_path else None,
        )

    if message.get("fatal"):
        raise FairStartViolationError(message["error"])

    message_witness = witness_from_payload(message.get("fair_start_witness"))
    if message_witness is not None:
        fair_start_witness = message_witness
    fair_start_error = message.get("fair_start_error")

    if message["ok"]:
        return SolverRun(
            solver=solver_name,
            time_limit_seconds=time_limit_seconds,
            actual_time_seconds=elapsed,
            watchdog_limit_seconds=watchdog_seconds,
            watchdog_killed=False,
            solution=solution_model(**message["solution"]),
            fair_start_witness=fair_start_witness,
            fair_start_valid=fair_start_error is None,
            fair_start_error=fair_start_error,
            run_error=None,
            exit_code=process.exitcode,
            solver_stdout_path=str(stdout_path) if stdout_path else None,
            solver_stderr_path=str(stderr_path) if stderr_path else None,
        )

    return SolverRun(
        solver=solver_name,
        time_limit_seconds=time_limit_seconds,
        actual_time_seconds=elapsed,
        watchdog_limit_seconds=watchdog_seconds,
        watchdog_killed=False,
        solution=None,
        fair_start_witness=fair_start_witness,
        fair_start_valid=fair_start_error is None,
        fair_start_error=fair_start_error,
        run_error=message["error"],
        exit_code=process.exitcode,
        solver_stdout_path=str(stdout_path) if stdout_path else None,
        solver_stderr_path=str(stderr_path) if stderr_path else None,
    )


def _process_context() -> mp.context.BaseContext:
    if "fork" in mp.get_all_start_methods():
        return mp.get_context("fork")
    return mp.get_context()


def _run_solver_child(
    benchmark_name: str,
    solver_name: str,
    solver_factory,
    instance: Any,
    solver_input_hash: str | None,
    time_limit_seconds: int,
    output_queue,
    stdout_path: str | None,
    stderr_path: str | None,
    capture_solver_output: bool,
    show_solver_output: bool,
) -> None:
    if hasattr(os, "setsid"):
        os.setsid()
    stdout = Path(stdout_path) if stdout_path and capture_solver_output else None
    stderr = Path(stderr_path) if stderr_path and capture_solver_output else None
    with capture_output(
        stdout_path=stdout,
        stderr_path=stderr,
        show_output=show_solver_output,
    ):
        latest_witness = None

        def record_witness(witness) -> None:
            nonlocal latest_witness
            validate_fair_start_witness(
                witness,
                benchmark_name=benchmark_name,
                solver_name=solver_name,
            )
            latest_witness = witness
            output_queue.put(
                {
                    "event": "fair_start_witness",
                    "fair_start_witness": witness_to_payload(witness),
                }
            )

        try:
            with (
                fair_start_input_hash(solver_input_hash),
                fair_start_recorder(record_witness),
            ):
                solver = solver_factory(
                    method=solver_name, time_limit=time_limit_seconds
                )
                result = solver(instance, time_limit_seconds)
            solver_output = validate_solver_result(
                result,
                benchmark_name=benchmark_name,
                solver_name=solver_name,
            )
            latest_witness = solver_output.fair_start_witness
            solution = solver_output.solution
            if solution is None:
                raise NoSolutionFoundError(f"{solver_name} returned no solution")
            output_queue.put(
                {
                    "ok": True,
                    "solution": _solution_payload(solution),
                    "fair_start_witness": witness_to_payload(latest_witness),
                    "fair_start_error": None,
                }
            )
        except FairStartViolationError as exc:
            traceback.print_exc()
            output_queue.put(
                {
                    "ok": False,
                    "fatal": True,
                    "error": f"{exc.__class__.__name__}: {exc}",
                }
            )
        except Exception as exc:
            traceback.print_exc()
            if latest_witness is None:
                output_queue.put(
                    {
                        "ok": False,
                        "fatal": True,
                        "error": (
                            "FairStartViolationError: "
                            f"{solver_name} failed before emitting a fair-start "
                            f"witness: {exc.__class__.__name__}: {exc}"
                        ),
                    }
                )
                return
            output_queue.put(
                {
                    "ok": False,
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "fair_start_witness": witness_to_payload(latest_witness),
                    "fair_start_error": None,
                }
            )


def _solution_payload(solution: Any) -> dict[str, Any]:
    if hasattr(solution, "model_dump"):
        return solution.model_dump(mode="json")
    return solution.dict()


def _collect_child_messages(
    output_queue,
    *,
    result_message: dict[str, Any] | None = None,
    fair_start_witness: Any | None = None,
    wait_seconds: float = 1.0,
) -> tuple[dict[str, Any] | None, Any | None]:
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            message = (
                output_queue.get(timeout=0.05)
                if time.monotonic() < deadline
                else output_queue.get_nowait()
            )
        except queue_module.Empty:
            if result_message is not None or time.monotonic() >= deadline:
                break
            continue

        witness = witness_from_payload(message.get("fair_start_witness"))
        if witness is not None:
            fair_start_witness = witness
        if message.get("event") == "fair_start_witness":
            continue
        result_message = message
    return result_message, fair_start_witness


def _terminate_process_tree(process) -> None:
    _signal_process_tree(process, signal.SIGTERM)
    process.join(0.2)
    if not process.is_alive():
        return

    _signal_process_tree(process, signal.SIGKILL)
    process.join(1.0)


def _signal_process_tree(process, sig: signal.Signals) -> None:
    signalled = False
    if hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, sig)
            signalled = True
        except ProcessLookupError:
            pass
        except PermissionError:
            pass
    if signalled:
        return
    try:
        os.kill(process.pid, sig)
    except ProcessLookupError:
        return
