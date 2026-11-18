"""Load hospital-at-scale instances from the committed, hash-pinned corpus."""

from __future__ import annotations

from pathlib import Path

from hospital_scale_bench.domain.models import Employee, Hub, Instance, Shift
from solverforge_bench.corpus import (
    CorpusError,
    group_names,
    instance_entries,
    read_document,
)

__all__ = [
    "CorpusError",
    "group_names",
    "instance_entries",
    "instance_from_document",
    "load_instance",
    "load_witness",
]


def load_instance(data_dir: Path, entry: dict) -> Instance:
    document = read_document(data_dir, entry["instance_path"], entry["instance_sha256"])
    return instance_from_document(document)


def load_witness(data_dir: Path, entry: dict) -> list[str]:
    document = read_document(data_dir, entry["witness_path"], entry["witness_sha256"])
    if document["name"] != entry["name"]:
        raise CorpusError(f"witness {entry['witness_path']} names {document['name']}")
    return list(document["assignments"])


def instance_from_document(document: dict) -> Instance:
    return Instance(
        name=document["name"],
        horizon_days=int(document["horizon_days"]),
        hubs=tuple(
            Hub(hub["name"], int(hub["x"]), int(hub["y"])) for hub in document["hubs"]
        ),
        skills=tuple(document["skills"]),
        skill_hubs=tuple(int(hub) for hub in document["skill_hubs"]),
        employees=tuple(
            Employee(
                id=employee["id"],
                home_hub=int(employee["home_hub"]),
                skills=tuple(employee["skills"]),
                unavailable_days=tuple(employee["unavailable_days"]),
                desired_days=tuple(employee["desired_days"]),
                undesired_days=tuple(employee["undesired_days"]),
            )
            for employee in document["employees"]
        ),
        shifts=tuple(
            Shift(
                id=shift["id"],
                start=int(shift["start"]),
                end=int(shift["end"]),
                hub=int(shift["hub"]),
                required_skill=int(shift["required_skill"]),
            )
            for shift in document["shifts"]
        ),
    )
