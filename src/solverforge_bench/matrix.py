"""Exact benchmark matrix construction and completion tracking."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from solverforge_bench.model import BenchmarkCase, BenchmarkRow


@dataclass(frozen=True, order=True)
class BenchmarkMatrixKey:
    benchmark_name: str
    dataset: str
    dataset_set: str
    instance: str
    solver: str
    time_limit_seconds: int

    @classmethod
    def from_case(
        cls,
        *,
        benchmark_name: str,
        case: BenchmarkCase,
        solver: str,
        time_limit_seconds: int,
    ) -> "BenchmarkMatrixKey":
        return cls(
            benchmark_name=benchmark_name,
            dataset=case.dataset,
            dataset_set=case.dataset_set,
            instance=case.instance,
            solver=solver,
            time_limit_seconds=time_limit_seconds,
        )

    @classmethod
    def from_row(cls, row: BenchmarkRow) -> "BenchmarkMatrixKey":
        return cls(
            benchmark_name=row.benchmark_name,
            dataset=row.dataset,
            dataset_set=row.dataset_set,
            instance=row.instance,
            solver=row.solver,
            time_limit_seconds=row.time_limit_seconds,
        )

    def as_payload(self) -> list[str | int]:
        return [
            self.benchmark_name,
            self.dataset,
            self.dataset_set,
            self.instance,
            self.solver,
            self.time_limit_seconds,
        ]


@dataclass(frozen=True)
class BenchmarkMatrix:
    benchmark_name: str
    cases: tuple[BenchmarkCase, ...]
    solvers: tuple[str, ...]
    time_limits_seconds: tuple[int, ...]
    expected_keys: tuple[BenchmarkMatrixKey, ...]

    @classmethod
    def build(
        cls,
        *,
        benchmark_name: str,
        cases: Iterable[BenchmarkCase],
        solvers: Iterable[str],
        time_limits_seconds: Iterable[int],
    ) -> "BenchmarkMatrix":
        case_list = tuple(cases)
        solver_list = tuple(solvers)
        time_limit_list = tuple(time_limits_seconds)

        if not case_list:
            raise ValueError(
                f"Benchmark {benchmark_name!r} selected no cases; refusing an empty run"
            )
        if not solver_list:
            raise ValueError(
                f"Benchmark {benchmark_name!r} selected no solvers; refusing an empty run"
            )
        if not time_limit_list:
            raise ValueError(
                f"Benchmark {benchmark_name!r} selected no time limits; refusing an empty run"
            )

        duplicate_cases = _duplicates(
            (case.dataset, case.dataset_set, case.instance) for case in case_list
        )
        if duplicate_cases:
            raise ValueError(
                "Duplicate benchmark case identity is not allowed: "
                + ", ".join("/".join(item) for item in duplicate_cases)
            )

        duplicate_solvers = _duplicates(solver_list)
        if duplicate_solvers:
            raise ValueError(
                "Duplicate solver(s) are not allowed: " + ", ".join(duplicate_solvers)
            )

        invalid_time_limits = [
            value
            for value in time_limit_list
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ]
        if invalid_time_limits:
            raise ValueError(
                "Benchmark time limits must be positive integer seconds: "
                + ", ".join(repr(value) for value in invalid_time_limits)
            )
        duplicate_time_limits = _duplicates(time_limit_list)
        if duplicate_time_limits:
            raise ValueError(
                "Duplicate benchmark time limits are not allowed: "
                + ", ".join(str(value) for value in duplicate_time_limits)
            )

        expected_keys = tuple(
            sorted(
                BenchmarkMatrixKey.from_case(
                    benchmark_name=benchmark_name,
                    case=case,
                    solver=solver,
                    time_limit_seconds=time_limit,
                )
                for case in case_list
                for time_limit in time_limit_list
                for solver in solver_list
            )
        )
        return cls(
            benchmark_name=benchmark_name,
            cases=case_list,
            solvers=solver_list,
            time_limits_seconds=time_limit_list,
            expected_keys=expected_keys,
        )

    @property
    def expected_count(self) -> int:
        return len(self.expected_keys)

    @property
    def sha256(self) -> str:
        return self.hash_keys(self.expected_keys)

    def hash_keys(self, keys: Iterable[BenchmarkMatrixKey]) -> str:
        payload = {
            "benchmark_name": self.benchmark_name,
            "rows": [key.as_payload() for key in sorted(keys)],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


class BenchmarkMatrixTracker:
    def __init__(self, matrix: BenchmarkMatrix):
        self.matrix = matrix
        self._expected = set(matrix.expected_keys)
        self._observed: set[BenchmarkMatrixKey] = set()

    @property
    def observed_count(self) -> int:
        return len(self._observed)

    @property
    def observed_sha256(self) -> str:
        return self.matrix.hash_keys(self._observed)

    def ensure_can_observe(self, key: BenchmarkMatrixKey) -> None:
        if key not in self._expected:
            raise ValueError(f"Unexpected benchmark matrix row: {_format_key(key)}")
        if key in self._observed:
            raise ValueError(f"Duplicate benchmark matrix row: {_format_key(key)}")

    def mark_observed(self, key: BenchmarkMatrixKey) -> None:
        self.ensure_can_observe(key)
        self._observed.add(key)

    def observe_row(self, row: BenchmarkRow) -> None:
        self.mark_observed(BenchmarkMatrixKey.from_row(row))

    def assert_complete(self) -> None:
        missing = sorted(self._expected - self._observed)
        if not missing:
            return
        preview = ", ".join(_format_key(key) for key in missing[:5])
        suffix = "" if len(missing) <= 5 else f", ... ({len(missing)} total)"
        raise ValueError(f"Benchmark matrix is incomplete; missing {preview}{suffix}")


def _duplicates(values: Iterable[object]) -> list[object]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _format_key(key: BenchmarkMatrixKey) -> str:
    return (
        f"{key.benchmark_name}/{key.dataset}/{key.dataset_set}/{key.instance}/"
        f"{key.solver}/{key.time_limit_seconds}s"
    )
