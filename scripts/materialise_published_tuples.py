#!/usr/bin/env python3.14
"""Materialise the competition's published tuples as enumerable benchmarks.

The loader discovers an instance by the presence of a ``Solution_H_<hist>-WD_<weeks>``
directory, and uses that directory both to name the case and to attach its
reference. The competition published validated scores for tuples that ship no
such directory, so those tuples exist in the corpus and can never be benchmarked
even though their reference values are known.

This creates the directory structure for each published tuple, containing the
competition's own submission files where available. A tuple with no published
solution file still gets its directory, because the directory is what makes the
case enumerable; the scoring reference comes from the catalog, not from the
directory contents.

    scripts/materialise_published_tuples.py [--check]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
EMPLOYEE_DIR = ROOT / "scalar-variable/employee-scheduling/data/inrc2"
CATALOG = EMPLOYEE_DIR / "references.json"

#: Catalog keys use the loader's case name: "<instance>_H<h>_WD<weeks>".
TUPLE = re.compile(r"^(?P<instance>n\d+w\d+)_H(?P<history>\d+)_WD(?P<weeks>[\d-]+)$")


def published_tuples() -> dict[str, str]:
    """Tuples whose reference comes from the competition's validated results."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {
        name: entry.get("reference_detail", "")
        for name, entry in catalog["instances"].items()
        if str(entry.get("reference_detail", "")).startswith("best validated")
    }


def directory_name(name: str) -> str:
    match = TUPLE.match(name)
    assert match is not None, f"not a catalog case name: {name!r}"
    return f"Solution_H_{match.group('history')}-WD_{match.group('weeks')}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report, do not create")
    args = parser.parse_args(argv)

    created, existing, unshipped = [], [], []
    for name in sorted(published_tuples()):
        match = TUPLE.match(name)
        assert match is not None
        instance, history, weeks = (
            match.group("instance"),
            match.group("history"),
            match.group("weeks"),
        )
        instance_dir = EMPLOYEE_DIR / instance
        if not instance_dir.is_dir():
            unshipped.append(name)
            continue
        needed = [instance_dir / f"H0-{instance}-{history}.txt"]
        needed += [
            instance_dir / f"WD-{instance}-{week}.txt" for week in weeks.split("-")
        ]
        if not all(path.exists() for path in needed):
            unshipped.append(name)
            continue
        target = instance_dir / directory_name(name)
        if target.exists():
            existing.append(name)
            continue
        if not args.check:
            target.mkdir()
        created.append(name)

    verb = "would create" if args.check else "created"
    print(f"published tuples      : {len(published_tuples())}")
    print(f"{verb:22}: {len(created)}")
    print(f"already present       : {len(existing)}")
    print(f"no corpus files       : {len(unshipped)}")
    for name in unshipped:
        print(f"   {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
