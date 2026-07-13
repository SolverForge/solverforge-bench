#!/usr/bin/env python3.14
"""Verify separate native and Python SolverForge configs stay equivalent."""

from __future__ import annotations

import difflib
import hashlib
import json
import sys
import tomllib
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

CONFIG_PAIRS = {
    "cvrp": (
        REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/solverforge/solver.toml",
        REPO_ROOT / "list-variable/cvrp/src/cvrp_bench/solver/solverforge_py.toml",
    ),
    "employee-scheduling": (
        REPO_ROOT
        / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/solverforge_nrp/solver.toml",
        REPO_ROOT
        / "scalar-variable/employee-scheduling/src/employee_scheduling_bench/solver/solverforge_py.toml",
    ),
    "job-shop-scheduling": (
        REPO_ROOT
        / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/solverforge_jssp/solver.toml",
        REPO_ROOT
        / "scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/solverforge_py.toml",
    ),
}

# These hashes pin the strongest previously qualified policies. Equality alone
# is insufficient: both copies could otherwise be weakened in the same edit.
QUALIFIED_POLICY_SHA256 = {
    "cvrp": "dd2afa37926753a1253816af4388247a8998c7f17c73b35f35b91406a099baef",
    "employee-scheduling": (
        "a0ac3ed7c1c6ce2ce51fbc780d556d2f252b83aaeb96a2f1f016307ba5dd2d10"
    ),
    "job-shop-scheduling": (
        "fa3c6ea67c3de08a5e7988768022c4ebded9e43211542f4662381ddf889a178f"
    ),
}


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as config_file:
        return tomllib.load(config_file)


def _canonical_json(config: dict[str, Any], *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(config, indent=2, sort_keys=True) + "\n"
    return json.dumps(config, separators=(",", ":"), sort_keys=True)


def _policy_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(config).encode()).hexdigest()


def verify_solverforge_config_parity() -> list[str]:
    failures: list[str] = []
    for benchmark, (native_path, python_path) in CONFIG_PAIRS.items():
        try:
            native_config = _load(native_path)
            python_config = _load(python_path)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            failures.append(f"{benchmark}: cannot load SolverForge config: {exc}")
            continue

        if native_config != python_config:
            diff = "".join(
                difflib.unified_diff(
                    _canonical_json(native_config, pretty=True).splitlines(True),
                    _canonical_json(python_config, pretty=True).splitlines(True),
                    fromfile=str(native_path.relative_to(REPO_ROOT)),
                    tofile=str(python_path.relative_to(REPO_ROOT)),
                )
            )
            failures.append(
                f"{benchmark}: native and Python SolverForge configs differ:\n{diff}"
            )

        native_hash = _policy_hash(native_config)
        qualified_hash = QUALIFIED_POLICY_SHA256[benchmark]
        if native_hash != qualified_hash:
            failures.append(
                f"{benchmark}: policy hash {native_hash} does not match the "
                f"qualified strongest-policy hash {qualified_hash}"
            )

    return failures


def main() -> None:
    failures = verify_solverforge_config_parity()
    if failures:
        for failure in failures:
            print(f"SolverForge config parity failure: {failure}", file=sys.stderr)
        raise SystemExit(1)

    for benchmark, (native_path, python_path) in CONFIG_PAIRS.items():
        print(
            f"SolverForge config parity passed: {benchmark}: "
            f"{native_path.relative_to(REPO_ROOT)} == "
            f"{python_path.relative_to(REPO_ROOT)}"
        )


if __name__ == "__main__":
    main()
