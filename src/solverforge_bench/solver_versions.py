"""Solver runtime version and content provenance discovery."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
import xml.etree.ElementTree as ET
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Iterable

from solverforge_bench.model import SolverVersion
from solverforge_bench.solverforge_config import solver_config_policy_sha256


Resolver = Callable[[str], SolverVersion]
PROVENANCE_SCHEMA_VERSION = 1


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


def python_distribution_version(
    distribution: str,
    *,
    solver_config_path: Path | None = None,
) -> Resolver:
    source = f"python-distribution:{distribution}"

    def resolve(solver: str) -> SolverVersion:
        try:
            version, artifact, distribution_details = _distribution_evidence(
                distribution
            )
            metadata = _provenance_metadata(
                runtime_artifacts=[artifact],
                input_paths=_optional_path(solver_config_path),
                details=distribution_details,
                solver_config_path=solver_config_path,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return unknown_solver_version(
                solver,
                source=source,
                metadata={"error": str(exc)},
            )
        return SolverVersion(
            solver=solver,
            version=version,
            source=source,
            metadata=metadata,
        )

    return resolve


def cargo_dependency_version(
    cargo_toml: Path,
    dependency: str,
    *,
    runtime_distribution: str | None = None,
    runtime_paths: Iterable[Path] = (),
    solver_config_path: Path | None = None,
) -> Resolver:
    cargo_lock = cargo_toml.with_name("Cargo.lock")
    source = f"cargo-lock:{cargo_lock}:{dependency}"

    def resolve(solver: str) -> SolverVersion:
        try:
            dependency_details = _locked_cargo_dependency(
                cargo_toml=cargo_toml,
                cargo_lock=cargo_lock,
                dependency=dependency,
            )
            runtime_artifacts: list[dict[str, Any]] = []
            details: dict[str, Any] = {
                "cargo_dependency": dependency_details,
            }
            if runtime_distribution is not None:
                _, artifact, distribution_details = _distribution_evidence(
                    runtime_distribution
                )
                runtime_artifacts.append(artifact)
                details.update(distribution_details)
            runtime_artifacts.extend(
                _hashed_file(path, kind="native_binary") for path in runtime_paths
            )
            metadata = _provenance_metadata(
                runtime_artifacts=runtime_artifacts,
                input_paths=[
                    cargo_toml,
                    cargo_lock,
                    *_optional_path(solver_config_path),
                ],
                details=details,
                solver_config_path=solver_config_path,
            )
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            tomllib.TOMLDecodeError,
        ) as exc:
            return unknown_solver_version(
                solver,
                source=source,
                metadata={"error": str(exc)},
            )
        return SolverVersion(
            solver=solver,
            version=dependency_details["version"],
            source=source,
            metadata=metadata,
        )

    return resolve


def executable_version(executable: Path, *args: str) -> Resolver:
    command = [str(executable), *(args or ("--version",))]
    source = f"executable:{executable}"

    def resolve(solver: str) -> SolverVersion:
        try:
            artifact = _hashed_file(executable, kind="executable")
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
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
        metadata = _provenance_metadata(
            runtime_artifacts=[artifact],
            details={
                "command": command,
                "version_output": output.strip(),
            },
        )
        return SolverVersion(
            solver=solver,
            version=match.group(0),
            source=source,
            metadata=metadata,
        )

    return resolve


def maven_property_version(
    pom: Path,
    property_name: str,
    *,
    artifact: Path,
) -> Resolver:
    source = f"maven-property:{pom}:{property_name}"

    def resolve(solver: str) -> SolverVersion:
        try:
            root = ET.parse(pom).getroot()
            version = _maven_property(root, property_name)
            metadata = _provenance_metadata(
                runtime_artifacts=[_hashed_file(artifact, kind="jar")],
                input_paths=[pom],
                details={"maven_property": property_name},
            )
        except (OSError, ET.ParseError, ValueError) as exc:
            return unknown_solver_version(
                solver,
                source=source,
                metadata={"error": str(exc)},
            )
        return SolverVersion(
            solver=solver,
            version=version,
            source=source,
            metadata=metadata,
        )

    return resolve


def _locked_cargo_dependency(
    *,
    cargo_toml: Path,
    cargo_lock: Path,
    dependency: str,
) -> dict[str, str]:
    with cargo_toml.open("rb") as handle:
        manifest = tomllib.load(handle)
    dependency_spec = manifest.get("dependencies", {}).get(dependency)
    if dependency_spec is None:
        raise ValueError(f"{cargo_toml}: dependency {dependency!r} is not declared")
    if isinstance(dependency_spec, str):
        requirement = dependency_spec
    elif isinstance(dependency_spec, dict):
        requirement = dependency_spec.get("version")
    else:
        requirement = None
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError(
            f"{cargo_toml}: dependency {dependency!r} has no registry version"
        )

    with cargo_lock.open("rb") as handle:
        lock = tomllib.load(handle)
    packages = [
        package
        for package in lock.get("package", [])
        if package.get("name") == dependency
    ]
    exact_requirement = requirement.strip().lstrip("=").strip()
    exact_matches = [
        package for package in packages if package.get("version") == exact_requirement
    ]
    if len(exact_matches) == 1:
        package = exact_matches[0]
    elif len(packages) == 1:
        package = packages[0]
    else:
        raise ValueError(
            f"{cargo_lock}: cannot resolve one locked {dependency!r} package"
        )

    locked_source = package.get("source")
    checksum = package.get("checksum")
    version = package.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{cargo_lock}: locked {dependency!r} version is missing")
    if not isinstance(locked_source, str) or not locked_source.startswith("registry+"):
        raise ValueError(
            f"{cargo_lock}: {dependency!r} is not backed by a registry source"
        )
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError(f"{cargo_lock}: {dependency!r} registry checksum is missing")
    return {
        "name": dependency,
        "manifest_requirement": requirement,
        "version": version,
        "source": locked_source,
        "checksum": checksum,
    }


def _maven_property(root: ET.Element, property_name: str) -> str:
    namespace_match = re.match(r"\{(?P<namespace>.*)\}", root.tag)
    namespace = namespace_match.group("namespace") if namespace_match else ""
    prefix = f"{{{namespace}}}" if namespace else ""
    properties = root.find(f"{prefix}properties")
    element = properties.find(f"{prefix}{property_name}") if properties else None
    if element is None or not element.text or not element.text.strip():
        raise ValueError(f"Maven property {property_name!r} was not found")
    return element.text.strip()


def _distribution_evidence(
    distribution: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    try:
        resolved = importlib_metadata.distribution(distribution)
    except importlib_metadata.PackageNotFoundError as exc:
        raise ValueError(
            f"Python distribution {distribution!r} is not installed"
        ) from exc

    files = resolved.files
    if not files:
        raise ValueError(f"Python distribution {distribution!r} has no file manifest")
    file_records = []
    for relative in sorted(files, key=str):
        relative_text = str(relative)
        if _exclude_distribution_file(relative_text):
            continue
        path = Path(resolved.locate_file(relative))
        if not path.is_file():
            raise ValueError(
                f"Python distribution {distribution!r} file is missing: {relative_text}"
            )
        file_records.append(
            {
                "path": relative_text,
                "sha256": _sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    if not file_records:
        raise ValueError(
            f"Python distribution {distribution!r} has no hashable runtime files"
        )

    canonical_name = resolved.metadata.get("Name") or distribution
    manifest_payload = {
        "name": canonical_name,
        "version": resolved.version,
        "files": file_records,
    }
    manifest_sha256 = _canonical_sha256(manifest_payload)
    artifact = {
        "kind": "python_distribution",
        "name": canonical_name,
        "version": resolved.version,
        "sha256": manifest_sha256,
        "size": sum(record["size"] for record in file_records),
        "file_count": len(file_records),
    }
    details: dict[str, Any] = {
        "distribution_files": file_records,
    }
    direct_url = resolved.read_text("direct_url.json")
    if direct_url:
        details["direct_url"] = json.loads(direct_url)
    return resolved.version, artifact, details


def _exclude_distribution_file(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        normalized.endswith(".pyc")
        or "/__pycache__/" in f"/{normalized}"
        or normalized.endswith(".dist-info/RECORD")
    )


def _provenance_metadata(
    *,
    runtime_artifacts: Iterable[dict[str, Any]],
    input_paths: Iterable[Path] = (),
    details: dict[str, Any] | None = None,
    solver_config_path: Path | None = None,
) -> dict[str, Any]:
    artifacts = list(runtime_artifacts)
    if not artifacts:
        raise ValueError("Solver provenance has no runtime artifact")
    payload: dict[str, Any] = {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "runtime_artifacts": artifacts,
        "inputs": [_hashed_file(path, kind="source_input") for path in input_paths],
    }
    if solver_config_path is not None:
        payload["solver_config_policy_sha256"] = solver_config_policy_sha256(
            solver_config_path
        )
    if details:
        payload.update(details)
    payload["provenance_sha256"] = _canonical_sha256(payload)
    return payload


def _hashed_file(path: Path, *, kind: str) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"Required {kind} does not exist: {path}")
    return {
        "kind": kind,
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
        "size": resolved.stat().st_size,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _optional_path(path: Path | None) -> list[Path]:
    return [] if path is None else [path]
