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
    solver_name: str,
    solver_factory: Callable[..., Callable[[Any, int], Any]],
    solution_model: type,
    instance: Any,
    time_limit_seconds: int,
    watchdog_seconds: float,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    capture_solver_output: bool = True,
    show_solver_output: bool = True,
) -> SolverRun:
    """Pass the benchmark budget to the solver and wait up to watchdog_seconds."""

    ctx = _process_context()
    output_queue = ctx.Queue(maxsize=1)
    process = ctx.Process(
        target=_run_solver_child,
        args=(
            solver_name,
            solver_factory,
            instance,
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
    process.join(watchdog_seconds)
    elapsed = time.monotonic() - started

    if process.is_alive():
        _terminate_process_tree(process)
        elapsed = time.monotonic() - started
        return SolverRun(
            solver=solver_name,
            time_limit_seconds=time_limit_seconds,
            actual_time_seconds=elapsed,
            watchdog_limit_seconds=watchdog_seconds,
            watchdog_killed=True,
            solution=None,
            run_error=(
                f"WatchdogTimeout: {solver_name} exceeded watchdog limit "
                f"({elapsed:.6f}s > {watchdog_seconds:.6f}s)"
            ),
            exit_code=process.exitcode,
            solver_stdout_path=str(stdout_path) if stdout_path else None,
            solver_stderr_path=str(stderr_path) if stderr_path else None,
        )

    try:
        message = output_queue.get_nowait()
    except queue_module.Empty:
        return SolverRun(
            solver=solver_name,
            time_limit_seconds=time_limit_seconds,
            actual_time_seconds=elapsed,
            watchdog_limit_seconds=watchdog_seconds,
            watchdog_killed=False,
            solution=None,
            run_error=(
                f"RuntimeError: {solver_name} exited without producing a result "
                f"(exit {process.exitcode})"
            ),
            exit_code=process.exitcode,
            solver_stdout_path=str(stdout_path) if stdout_path else None,
            solver_stderr_path=str(stderr_path) if stderr_path else None,
        )

    if message["ok"]:
        return SolverRun(
            solver=solver_name,
            time_limit_seconds=time_limit_seconds,
            actual_time_seconds=elapsed,
            watchdog_limit_seconds=watchdog_seconds,
            watchdog_killed=False,
            solution=solution_model(**message["solution"]),
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
    solver_name: str,
    solver_factory,
    instance: Any,
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
        try:
            solver = solver_factory(method=solver_name, time_limit=time_limit_seconds)
            solution = solver(instance, time_limit_seconds)
            if solution is None:
                raise NoSolutionFoundError(f"{solver_name} returned no solution")
            output_queue.put({"ok": True, "solution": _solution_payload(solution)})
        except Exception as exc:
            traceback.print_exc()
            output_queue.put(
                {
                    "ok": False,
                    "error": f"{exc.__class__.__name__}: {exc}",
                }
            )


def _solution_payload(solution: Any) -> dict[str, Any]:
    if hasattr(solution, "model_dump"):
        return solution.model_dump(mode="json")
    return solution.dict()


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
