"""Hash-pinned generated corpora shared by the huge-scale benchmarks.

A generated corpus is committed as deterministic gzip JSON documents plus a
``manifest.json`` that pins each file's SHA-256. Loading refuses any file whose
bytes differ from the manifest, and ``render_check`` lets a generator prove the
committed bytes still reproduce.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

MANIFEST_NAME = "manifest.json"


class CorpusError(ValueError):
    """Raised when a committed corpus file does not match its manifest."""


def encode_document(document: dict) -> bytes:
    """Deterministic gzip JSON: sorted keys, compact separators, zero mtime."""

    raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return gzip.compress(raw, compresslevel=9, mtime=0)


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_manifest(data_dir: Path) -> dict:
    return json.loads((data_dir / MANIFEST_NAME).read_text(encoding="utf-8"))


def instance_entries(data_dir: Path) -> list[dict]:
    return list(load_manifest(data_dir)["instances"])


def group_names(data_dir: Path, group: str) -> list[str]:
    groups = load_manifest(data_dir)["groups"]
    if group not in groups:
        raise CorpusError(
            f"Unknown dataset set {group!r}; available: {', '.join(sorted(groups))}"
        )
    return list(groups[group])


def read_document(data_dir: Path, relative_path: str, expected_sha256: str) -> dict:
    """Read a gzip JSON document after checking its committed SHA-256."""

    payload = (data_dir / relative_path).read_bytes()
    actual = sha256_hex(payload)
    if actual != expected_sha256:
        raise CorpusError(
            f"{relative_path} sha256 {actual} does not match manifest {expected_sha256}"
        )
    return json.loads(gzip.decompress(payload))


def write_or_check(
    data_dir: Path, files: dict[str, bytes], *, check: bool
) -> list[str]:
    """Write rendered files, or return the paths whose committed bytes drifted."""

    if check:
        return [
            relative
            for relative, payload in files.items()
            if not (data_dir / relative).is_file()
            or (data_dir / relative).read_bytes() != payload
        ]
    for relative, payload in files.items():
        path = data_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return []


def manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
