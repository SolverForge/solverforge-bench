"""TOML configuration loading for the benchmark harness."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BenchmarkConfigError(ValueError):
    """Raised when a benchmark TOML config is invalid."""


@dataclass(frozen=True)
class BenchmarkConfig:
    path: Path | None
    benchmark: str | None
    values: dict[str, Any]
    benchmark_values: dict[str, dict[str, Any]]


ROOT_KEYS = {
    "benchmark",
    "solver",
    "time_limits",
    "wall_time_tolerance",
    "watchdog_multiplier",
    "watchdog_grace_seconds",
    "output",
    "run_kind",
    "nightly",
    "release_tag",
}
TABLE_KEYS = {"postgres", "benchmarks", "logging"}
POSTGRES_KEYS = {"save", "url"}
LOGGING_KEYS = {
    "level",
    "dir",
    "file",
    "show_solver_output",
    "capture_solver_output",
}
BENCHMARK_KEYS = {
    "cvrp": {"num_instances"},
    "employee-scheduling": {"dataset_set", "datasets"},
    "job-shop-scheduling": {"dataset_set", "datasets"},
}
RUN_KIND_CHOICES = ("quick", "candidate", "tag")


def config_path_from_argv(argv: list[str]) -> Path | None:
    for index, value in enumerate(argv):
        if value == "--config":
            try:
                return Path(argv[index + 1])
            except IndexError as exc:
                raise BenchmarkConfigError("--config requires a path") from exc
        if value.startswith("--config="):
            return Path(value.split("=", maxsplit=1)[1])
    return None


def load_benchmark_config(
    path: Path | None, *, benchmark_names: set[str]
) -> BenchmarkConfig:
    if path is None:
        return BenchmarkConfig(
            path=None, benchmark=None, values={}, benchmark_values={}
        )

    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except OSError as exc:
        raise BenchmarkConfigError(
            f"Cannot read benchmark config {path}: {exc}"
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise BenchmarkConfigError(
            f"Invalid TOML in benchmark config {path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise BenchmarkConfigError("Benchmark config root must be a TOML table")

    unknown_root = set(raw) - ROOT_KEYS - TABLE_KEYS
    if unknown_root:
        raise BenchmarkConfigError(
            f"Unknown benchmark config key(s): {', '.join(sorted(unknown_root))}"
        )

    values = {key: raw[key] for key in ROOT_KEYS if key in raw and key != "benchmark"}

    benchmark = raw.get("benchmark")
    if benchmark is not None and benchmark not in benchmark_names:
        available = ", ".join(sorted(benchmark_names))
        raise BenchmarkConfigError(
            f"Unknown benchmark in config: {benchmark}. Available: {available}"
        )

    _merge_postgres_table(values, raw.get("postgres"))
    _merge_logging_table(values, raw.get("logging"))
    benchmark_values = _benchmark_tables(raw.get("benchmarks"), benchmark_names)
    _validate_values(values)
    for table_values in benchmark_values.values():
        _validate_values(table_values)
    return BenchmarkConfig(
        path=path,
        benchmark=benchmark,
        values=values,
        benchmark_values=benchmark_values,
    )


def apply_benchmark_config(args: Any, config: BenchmarkConfig) -> None:
    values = {
        **config.values,
        **config.benchmark_values.get(args.spec.name, {}),
    }
    for key, value in values.items():
        if getattr(args, key, None) is None:
            setattr(args, key, _coerce_value(key, value))
    if config.path is not None:
        args.config = config.path


def finalize_benchmark_defaults(
    args: Any, *, postgres_url_enables_save: bool = False
) -> None:
    if args.wall_time_tolerance is None:
        args.wall_time_tolerance = 1.1
    if args.watchdog_multiplier is None:
        args.watchdog_multiplier = 1.25
    if args.watchdog_grace_seconds is None:
        args.watchdog_grace_seconds = 5.0
    if args.run_kind is None:
        args.run_kind = "candidate"
    if args.nightly is None:
        args.nightly = False
    if args.save_postgres is None:
        args.save_postgres = False
    if args.log_level is None:
        args.log_level = "INFO"
    if args.show_solver_output is None:
        args.show_solver_output = True
    if args.capture_solver_output is None:
        args.capture_solver_output = True
    if postgres_url_enables_save and args.postgres_url:
        args.save_postgres = True


def finalize_run_catalog(
    args: Any, *, run_kind_from_cli: bool, release_tag_from_cli: bool
) -> None:
    if run_kind_from_cli and args.run_kind != "tag" and not release_tag_from_cli:
        args.release_tag = None

    if args.release_tag is not None and not args.release_tag.strip():
        raise BenchmarkConfigError("--release-tag must not be blank.")
    if args.run_kind == "tag" and not args.release_tag:
        raise BenchmarkConfigError(
            "--release-tag is required when --run-kind tag is used."
        )
    if args.run_kind != "tag" and args.release_tag:
        raise BenchmarkConfigError("--release-tag is only valid with --run-kind tag.")


def _merge_postgres_table(values: dict[str, Any], table: Any) -> None:
    if table is None:
        return
    if not isinstance(table, dict):
        raise BenchmarkConfigError("[postgres] must be a TOML table")
    unknown = set(table) - POSTGRES_KEYS
    if unknown:
        raise BenchmarkConfigError(
            f"Unknown [postgres] key(s): {', '.join(sorted(unknown))}"
        )
    if "save" in table:
        _set_once(values, "save_postgres", table["save"], "postgres.save")
    if "url" in table:
        _set_once(values, "postgres_url", table["url"], "postgres.url")


def _merge_logging_table(values: dict[str, Any], table: Any) -> None:
    if table is None:
        return
    if not isinstance(table, dict):
        raise BenchmarkConfigError("[logging] must be a TOML table")
    unknown = set(table) - LOGGING_KEYS
    if unknown:
        raise BenchmarkConfigError(
            f"Unknown [logging] key(s): {', '.join(sorted(unknown))}"
        )
    key_map = {
        "level": "log_level",
        "dir": "log_dir",
        "file": "log_file",
        "show_solver_output": "show_solver_output",
        "capture_solver_output": "capture_solver_output",
    }
    for key, value in table.items():
        _set_once(values, key_map[key], value, f"logging.{key}")


def _benchmark_tables(
    table: Any, benchmark_names: set[str]
) -> dict[str, dict[str, Any]]:
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise BenchmarkConfigError("[benchmarks] must be a TOML table")
    unknown_benchmarks = set(table) - benchmark_names
    if unknown_benchmarks:
        raise BenchmarkConfigError(
            "Unknown [benchmarks] table(s): " f"{', '.join(sorted(unknown_benchmarks))}"
        )
    parsed: dict[str, dict[str, Any]] = {}
    for benchmark_name, benchmark_values in table.items():
        if not isinstance(benchmark_values, dict):
            raise BenchmarkConfigError(
                f"[benchmarks.{benchmark_name}] must be a TOML table"
            )
        allowed = BENCHMARK_KEYS.get(benchmark_name, set())
        unknown = set(benchmark_values) - allowed
        if unknown:
            raise BenchmarkConfigError(
                f"Unknown [benchmarks.{benchmark_name}] key(s): "
                f"{', '.join(sorted(unknown))}"
            )
        parsed[benchmark_name] = dict(benchmark_values)
    return parsed


def _validate_values(values: dict[str, Any]) -> None:
    list_keys = {"solver", "time_limits", "datasets"}
    string_keys = {
        "dataset_set",
        "output",
        "run_kind",
        "release_tag",
        "postgres_url",
        "log_level",
        "log_dir",
        "log_file",
    }
    float_keys = {
        "wall_time_tolerance",
        "watchdog_multiplier",
        "watchdog_grace_seconds",
    }
    int_keys = {"num_instances"}
    bool_keys = {
        "nightly",
        "save_postgres",
        "show_solver_output",
        "capture_solver_output",
    }

    for key in list_keys & set(values):
        if not isinstance(values[key], list):
            raise BenchmarkConfigError(f"{key} must be a TOML array")
    for key in string_keys & set(values):
        if values[key] is not None and not isinstance(values[key], str):
            raise BenchmarkConfigError(f"{key} must be a string")
    for key in float_keys & set(values):
        if not isinstance(values[key], (int, float)):
            raise BenchmarkConfigError(f"{key} must be a number")
    for key in int_keys & set(values):
        if not isinstance(values[key], int):
            raise BenchmarkConfigError(f"{key} must be an integer")
    for key in bool_keys & set(values):
        if not isinstance(values[key], bool):
            raise BenchmarkConfigError(f"{key} must be true or false")
    if "run_kind" in values and values["run_kind"] not in RUN_KIND_CHOICES:
        available = ", ".join(RUN_KIND_CHOICES)
        raise BenchmarkConfigError(
            f"run_kind must be one of: {available}; got {values['run_kind']!r}"
        )


def _coerce_value(key: str, value: Any) -> Any:
    if key == "output" and value is not None:
        return Path(value)
    if key in {"log_dir", "log_file"} and value is not None:
        return Path(value)
    if key == "time_limits":
        return [int(item) for item in value]
    if key in {"solver", "datasets"}:
        return [str(item) for item in value]
    if key in {
        "wall_time_tolerance",
        "watchdog_multiplier",
        "watchdog_grace_seconds",
    }:
        return float(value)
    return value


def _set_once(values: dict[str, Any], key: str, value: Any, source_name: str) -> None:
    if key in values:
        raise BenchmarkConfigError(
            f"Config sets {key} more than once; remove the duplicate at {source_name}"
        )
    values[key] = value
