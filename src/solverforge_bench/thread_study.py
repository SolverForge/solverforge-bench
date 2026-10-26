"""Thread-count variants of the native SolverForge adapters, and their report.

`solverforge-t<N>` runs a native SolverForge adapter with N local-search
evaluators, the main director included. The variants compare SolverForge with
itself across thread counts, so they stay out of every suite's default matrix
and never enter cross-solver rankings; the thread study selects them
explicitly.

The report answers one question per instance and time budget: does the
multi-threaded run reach a better solution than the single-threaded one, and
what in the search explains it. Useful throughput counts only evaluations the
coordinator consumed; speculative evaluations are work parallel windows
discarded.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

THREAD_STUDY_COUNTS = (2, 4, 8)
_VARIANT_PREFIX = "solverforge-t"
# A cost difference inside this band is reported as a tie.
TIE_BAND_PERCENT = 0.5


def thread_variant_methods() -> list[str]:
    return [f"{_VARIANT_PREFIX}{count}" for count in THREAD_STUDY_COUNTS]


def thread_variant_count(method: str) -> int | None:
    """Move-thread count of a `solverforge-t<N>` method, or None for any other."""
    if not method.startswith(_VARIANT_PREFIX):
        return None
    suffix = method[len(_VARIANT_PREFIX) :]
    if not suffix.isdigit() or int(suffix) not in THREAD_STUDY_COUNTS:
        return None
    return int(suffix)


def solver_threads(method: str) -> int | None:
    """Thread count of the native SolverForge solver or one of its variants."""
    if method == "solverforge":
        return 1
    return thread_variant_count(method)


@dataclass(frozen=True)
class StudyRun:
    benchmark: str
    instance: str
    time_limit: int
    threads: int
    feasible: bool
    cost: float | None
    moves_evaluated: int
    moves_speculative: int
    step_count: int
    elapsed_ms: int

    @property
    def useful_evaluations_per_second(self) -> float | None:
        if self.elapsed_ms <= 0:
            return None
        return self.moves_evaluated * 1000 / self.elapsed_ms

    @property
    def speculative_share(self) -> float | None:
        total = self.moves_evaluated + self.moves_speculative
        return self.moves_speculative / total if total else None

    @property
    def evaluations_per_step(self) -> float | None:
        return self.moves_evaluated / self.step_count if self.step_count else None


def read_study_runs(paths: Iterable[Path]) -> list[StudyRun]:
    runs = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                threads = solver_threads(row["solver"])
                if threads is None:
                    continue
                telemetry = _telemetry(row.get("solver_metadata") or "")
                cost = row.get("cost") or None
                runs.append(
                    StudyRun(
                        benchmark=row["benchmark_name"],
                        instance=row["instance"],
                        time_limit=int(row["time_limit_seconds"]),
                        threads=threads,
                        feasible=row.get("hard_feasible") == "true",
                        cost=float(cost) if cost is not None else None,
                        moves_evaluated=int(telemetry.get("moves_evaluated") or 0),
                        moves_speculative=int(telemetry.get("moves_speculative") or 0),
                        step_count=int(telemetry.get("step_count") or 0),
                        elapsed_ms=int(telemetry.get("elapsed_ms") or 0),
                    )
                )
    return runs


def _telemetry(metadata: str) -> dict[str, Any]:
    if not metadata:
        return {}
    telemetry = json.loads(metadata).get("solverforge_telemetry")
    return telemetry if isinstance(telemetry, dict) else {}


def verdict(baseline: StudyRun, candidate: StudyRun) -> str:
    """Which thread count a user should pick for this cell, from cost alone."""
    if not candidate.feasible and baseline.feasible:
        return "1 thread"
    if candidate.feasible and not baseline.feasible:
        return f"{candidate.threads} threads"
    if baseline.cost is None or candidate.cost is None or baseline.cost == 0:
        return "n/a"
    delta = (candidate.cost - baseline.cost) / abs(baseline.cost) * 100
    if abs(delta) <= TIE_BAND_PERCENT:
        return "tie"
    return f"{candidate.threads} threads" if delta < 0 else "1 thread"


def render_report(runs: list[StudyRun]) -> str:
    """Markdown tables, one per benchmark, comparing every thread count to 1."""
    cells: dict[tuple[str, str, int], dict[int, StudyRun]] = {}
    for run in runs:
        cells.setdefault((run.benchmark, run.instance, run.time_limit), {})[
            run.threads
        ] = run
    lines = []
    for benchmark in sorted({key[0] for key in cells}):
        lines += [
            f"## {benchmark}",
            "",
            "| instance | budget | threads | cost | cost vs 1T | useful evals/s vs 1T"
            " | speculative share | evals/step | verdict |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for key in sorted(k for k in cells if k[0] == benchmark):
            by_threads = cells[key]
            baseline = by_threads.get(1)
            for threads in sorted(by_threads):
                run = by_threads[threads]
                lines.append(_report_row(key, run, baseline))
        lines.append("")
    return "\n".join(lines)


def _report_row(
    key: tuple[str, str, int], run: StudyRun, baseline: StudyRun | None
) -> str:
    _, instance, time_limit = key
    cost = _number(run.cost) if run.feasible else "infeasible"
    if baseline is None or run.threads == 1:
        cost_delta = throughput = decision = "—"
    else:
        cost_delta = _percent_change(baseline.cost, run.cost)
        throughput = _ratio(
            baseline.useful_evaluations_per_second, run.useful_evaluations_per_second
        )
        decision = verdict(baseline, run)
    return (
        f"| {instance} | {time_limit}s | {run.threads} | {cost} | {cost_delta}"
        f" | {throughput} | {_share(run.speculative_share)}"
        f" | {_number(run.evaluations_per_step)} | {decision} |"
    )


def _number(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}" if abs(value) >= 100 else f"{value:,.1f}"


def _percent_change(before: float | None, after: float | None) -> str:
    if before in (None, 0) or after is None:
        return "—"
    return f"{(after - before) / abs(before) * 100:+.1f}%"


def _ratio(before: float | None, after: float | None) -> str:
    if not before or after is None:
        return "—"
    return f"{after / before:.2f}x"


def _share(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"
