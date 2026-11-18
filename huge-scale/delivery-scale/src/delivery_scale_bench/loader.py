"""Load delivery-at-scale instances from the committed, hash-pinned corpus."""

from __future__ import annotations

from pathlib import Path

from delivery_scale_bench.domain.models import Delivery, Instance
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


def load_witness(data_dir: Path, entry: dict) -> list[list[str]]:
    document = read_document(data_dir, entry["witness_path"], entry["witness_sha256"])
    if document["name"] != entry["name"]:
        raise CorpusError(f"witness {entry['witness_path']} names {document['name']}")
    return [list(route) for route in document["routes"]]


def instance_from_document(document: dict) -> Instance:
    return Instance(
        name=document["name"],
        depot_x=int(document["depot"]["x"]),
        depot_y=int(document["depot"]["y"]),
        departure_time=int(document["departure_time"]),
        vehicle_count=int(document["vehicle_count"]),
        capacity=int(document["capacity"]),
        deliveries=tuple(
            Delivery(
                id=delivery["id"],
                x=int(delivery["x"]),
                y=int(delivery["y"]),
                demand=int(delivery["demand"]),
                min_start=int(delivery["min_start"]),
                max_end=int(delivery["max_end"]),
                service=int(delivery["service"]),
            )
            for delivery in document["deliveries"]
        ),
    )
