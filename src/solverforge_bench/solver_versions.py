"""Solver version discovery helpers for benchmark metadata."""

from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Callable, Iterable

from solverforge_bench.model import SolverVersion


Resolver = Callable[[str], SolverVersion]


def versions_for_solvers(
    solvers: Iterable[str], resolvers: dict[str, Resolver]
) -> dict[str, SolverVersion]:
    versions = {}
    for solver in solvers:
        resolver = resolvers.get(solver)
        versions[solver] = (
            resolver(solver)
            if resolver is not None
            else unknown_solver_version(solver, source="unregistered")
        )
    return versions


def unknown_solver_version(
    solver: str, *, source: str, metadata: dict[str, object] | None = None
) -> SolverVersion:
    return SolverVersion(
        solver=solver,
        version="unknown",
        source=source,
        metadata=metadata or {},
    )


def python_distribution_version(distribution: str) -> Resolver:
    def resolve(solver: str) -> SolverVersion:
        try:
            version = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError:
            return unknown_solver_version(
                solver,
                source=f"python-distribution:{distribution}",
                metadata={"error": "distribution_not_installed"},
            )
        return SolverVersion(
            solver=solver,
            version=version,
            source=f"python-distribution:{distribution}",
        )

    return resolve


def cargo_dependency_version(cargo_toml: Path, dependency: str) -> Resolver:
    pattern = re.compile(
        rf"^{re.escape(dependency)}\s*=\s*"
        rf"(?:\"(?P<string>[^\"]+)\"|\{{[^}}]*\bversion\s*=\s*\"(?P<table>[^\"]+)\")"
    )

    def resolve(solver: str) -> SolverVersion:
        try:
            for line in cargo_toml.read_text(encoding="utf-8").splitlines():
                match = pattern.search(line.strip())
                if match:
                    return SolverVersion(
                        solver=solver,
                        version=match.group("string") or match.group("table"),
                        source=f"cargo-dependency:{cargo_toml}:{dependency}",
                    )
        except OSError as exc:
            return unknown_solver_version(
                solver,
                source=f"cargo-dependency:{cargo_toml}:{dependency}",
                metadata={"error": str(exc)},
            )
        return unknown_solver_version(
            solver,
            source=f"cargo-dependency:{cargo_toml}:{dependency}",
            metadata={"error": "dependency_version_not_found"},
        )

    return resolve


def executable_version(executable: Path, *args: str) -> Resolver:
    command = [str(executable), *(args or ("--version",))]
    source = f"executable:{executable}"

    def resolve(solver: str) -> SolverVersion:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            return unknown_solver_version(
                solver,
                source=source,
                metadata={"error": str(exc), "command": command},
            )

        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        if result.returncode != 0:
            return unknown_solver_version(
                solver,
                source=source,
                metadata={
                    "error": f"exit {result.returncode}",
                    "command": command,
                    "output": output.strip(),
                },
            )

        match = re.search(r"\b\d+(?:\.\d+)+(?:[-+][A-Za-z0-9_.-]+)?\b", output)
        if not match:
            return unknown_solver_version(
                solver,
                source=source,
                metadata={
                    "error": "version_not_found",
                    "command": command,
                    "output": output.strip(),
                },
            )
        return SolverVersion(
            solver=solver,
            version=match.group(0),
            source=source,
            metadata={"command": command},
        )

    return resolve


def maven_property_version(pom: Path, property_name: str) -> Resolver:
    def resolve(solver: str) -> SolverVersion:
        try:
            root = ET.parse(pom).getroot()
        except (OSError, ET.ParseError) as exc:
            return unknown_solver_version(
                solver,
                source=f"maven-property:{pom}:{property_name}",
                metadata={"error": str(exc)},
            )

        namespace_match = re.match(r"\{(?P<namespace>.*)\}", root.tag)
        namespace = namespace_match.group("namespace") if namespace_match else ""
        prefix = f"{{{namespace}}}" if namespace else ""
        properties = root.find(f"{prefix}properties")
        element = properties.find(f"{prefix}{property_name}") if properties else None
        if element is not None and element.text and element.text.strip():
            return SolverVersion(
                solver=solver,
                version=element.text.strip(),
                source=f"maven-property:{pom}:{property_name}",
            )
        return unknown_solver_version(
            solver,
            source=f"maven-property:{pom}:{property_name}",
            metadata={"error": "property_not_found"},
        )

    return resolve
