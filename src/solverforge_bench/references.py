"""Versioned official reference catalog shared by every problem type.

A problem with no reference cost cannot report a mean gap, and an unlabelled
reference makes "0% gap" indistinguishable from a solver graded against its own
best result. Both are publication problems, so the reference for an instance is
resolved in one place, from one versioned file per problem, carrying the source
that published it and how strong the claim is.

Reference strength is not decoration. A *closed* instance has a proven optimum,
so a solver matching it has no gap; an *open* instance has a best-known upper
bound, so a solver matching it may still be above the true optimum. Comparing
across reference kinds is comparing different claims, which is why the kind
travels with the value instead of being inferred from it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

#: Filename of the versioned catalog beside each problem's instance data.
CATALOG_FILE = "references.json"

#: ``closed`` means the reference is a proven optimum; ``open`` means it is the
#: best known upper bound. Any other value is a typo, not a third state.
STATUS_CLOSED = "closed"
STATUS_OPEN = "open"
_VALID_STATUSES = (STATUS_CLOSED, STATUS_OPEN)

KNOWN_OPTIMUM = "known_optimum"
BEST_KNOWN_UPPER_BOUND = "best_known_upper_bound"

#: Key under which a catalog carries per-instance extra provenance. It is
#: optional; a catalog that omits it still resolves every reference.
NATIVE_FIELDS_KEY = "native_fields"


class ReferenceCatalogError(ValueError):
    """The catalog is absent, malformed, or silent about an instance."""


@dataclass(frozen=True)
class Reference:
    """One official reference value and the claim it supports."""

    instance: str
    reference_cost: float
    kind: str
    status: str
    source_name: str
    source_revision: str
    lower_bound: float | None = None
    upper_bound: float | None = None
    native_fields: dict[str, Any] | None = None

    @property
    def is_optimum(self) -> bool:
        return self.kind == KNOWN_OPTIMUM

    def gap(self, cost: float) -> float | None:
        """Relative distance from ``cost`` to the reference, or None if unknown."""
        if self.reference_cost in (None, 0) or cost is None:
            return None
        return (cost - self.reference_cost) / self.reference_cost

    def ratio(self, cost: float) -> float | None:
        """``cost`` divided by the reference, or None if the reference is unknown."""
        if not self.reference_cost or cost is None:
            return None
        return cost / self.reference_cost


@lru_cache(maxsize=16)
def load_catalog(data_dir: str) -> dict[str, Any]:
    """Load and validate the catalog that sits beside a problem's instances."""
    path = Path(data_dir) / CATALOG_FILE
    if not path.exists():
        raise ReferenceCatalogError(
            f"no reference catalog at {path}; a problem that cannot state its "
            f"references must say so rather than publish an unlabelled gap"
        )
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReferenceCatalogError(f"{path} is not valid JSON: {exc}") from exc

    source = catalog.get("source") or {}
    for field in ("name", "revision"):
        if not str(source.get(field, "")).strip():
            raise ReferenceCatalogError(f"{path} does not name its source {field}")
    instances = catalog.get("instances")
    if not isinstance(instances, dict) or not instances:
        raise ReferenceCatalogError(f"{path} carries no instances")

    for instance, entry in instances.items():
        if not isinstance(entry, dict):
            raise ReferenceCatalogError(f"{path}: {instance} is not an object")
        if entry.get("status") not in _VALID_STATUSES:
            raise ReferenceCatalogError(
                f"{path}: {instance} has status {entry.get('status')!r}, "
                f"expected one of {_VALID_STATUSES}"
            )
        value = entry.get("reference")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise ReferenceCatalogError(
                f"{path}: {instance} carries reference {value!r}, which is not a "
                f"positive number"
            )
    return catalog


def catalog_instances(data_dir: Path) -> frozenset[str]:
    """Instance names the catalog can resolve, for coverage checks."""
    return frozenset(load_catalog(str(data_dir))["instances"])


def reference_for(data_dir: Path, instance: str) -> Reference:
    """Resolve the official reference for one instance.

    A missing entry raises rather than returning None: silently dropping the
    reference would publish a run whose gap is computed against nothing.
    """
    catalog = load_catalog(str(data_dir))
    source = catalog["source"]
    try:
        entry = catalog["instances"][instance]
    except KeyError as exc:
        raise ReferenceCatalogError(
            f"instance {instance!r} has no entry in {Path(data_dir) / CATALOG_FILE}"
        ) from exc

    reference_cost = float(entry["reference"])
    status = entry["status"]
    lower = entry.get("lower_bound")
    upper = entry.get("upper_bound")
    return Reference(
        instance=instance,
        reference_cost=reference_cost,
        kind=KNOWN_OPTIMUM if status == STATUS_CLOSED else BEST_KNOWN_UPPER_BOUND,
        status=status,
        source_name=str(source["name"]),
        source_revision=str(source["revision"]),
        lower_bound=float(lower) if isinstance(lower, (int, float)) else reference_cost,
        upper_bound=float(upper) if isinstance(upper, (int, float)) else reference_cost,
        native_fields=dict(entry.get(NATIVE_FIELDS_KEY) or {}),
    )


def references_by_instance(
    data_dir: Path, instances: Iterable[str]
) -> dict[str, Reference]:
    """Resolve several instances at once, failing on the first gap."""
    return {instance: reference_for(data_dir, instance) for instance in instances}
