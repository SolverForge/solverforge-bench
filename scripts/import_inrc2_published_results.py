#!/usr/bin/env python3.14
"""Extract the INRC-II competition's validated results as reference values.

The competition published validated results for the late instances: for each
history/week tuple, the soft cost each finalist's solver actually achieved,
checked by the organising team's validator. The best of those is a defensible
best known upper bound for that tuple -- an external measurement, not ours.

This writes the published values into the employee-scheduling catalog. It reads
the workbooks and the bundled corpus, and runs no benchmark.

    scripts/import_inrc2_published_results.py <validated.xlsx> [--check]

The workbook is the competition's own artefact; keep it beside the catalog so a
value can be traced to the row it came from.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
EMPLOYEE_DIR = ROOT / "scalar-variable/employee-scheduling/data/inrc2"
CATALOG = EMPLOYEE_DIR / "references.json"

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
TUPLE = re.compile(r"^(?P<instance>n\d+w\d+)_(?P<history>\d+)_(?P<weeks>[\d-]+)$")


def sheet_cells(path: Path) -> list[tuple[str, str | None]]:
    """Read the first worksheet as (cell reference, value) pairs."""
    archive = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        raw = archive.read("xl/sharedStrings.xml").decode("utf-8", "replace")
        shared = [
            re.sub(r"<[^>]+>", "", s) for s in re.findall(r"<si>(.*?)</si>", raw, re.S)
        ]
    sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    cells: list[tuple[str, str | None]] = []
    for row in sheet.iter(f"{{{NS}}}row"):
        for cell in row.iter(f"{{{NS}}}c"):
            value = cell.find(f"{{{NS}}}v")
            if value is None:
                continue
            text = shared[int(value.text)] if cell.get("t") == "s" else value.text
            cells.append((cell.get("r") or "", text))
    return cells


def column_of(reference: str) -> str:
    return re.match(r"([A-Z]+)", reference).group(1)


def parse_validated_results(path: Path) -> dict[str, tuple[float, str]]:
    """Return the best validated score per instance and who produced it.

    A score of zero means every finalist's submission for that tuple failed
    validation, which is a statement about the submissions rather than a
    reference anyone can match, so it is not carried into the catalog.
    """
    cells = sheet_cells(path)
    by_row: dict[int, dict[str, str]] = {}
    for reference, text in cells:
        row = int(re.search(r"(\d+)", reference).group(1))
        by_row.setdefault(row, {})[column_of(reference)] = (
            text if text is not None else ""
        )

    # The first row of the sheet carries a single label cell ("Results") and the
    # header row names the teams. Identify both explicitly: guessing from cell
    # counts picks up the trailing "Average"/"Rank" summary rows instead, whose
    # values are placements, not costs.
    label_row = None
    for row in sorted(by_row):
        if by_row[row].get("A", "").strip().lower() == "results":
            label_row = row
            break
    if label_row is None:
        raise SystemExit(f"{path}: no 'Results' label row found")
    header_row = label_row + 1
    teams = {
        col: text
        for col, text in by_row.get(header_row, {}).items()
        if col != "A" and text
    }
    if len(teams) < 2:
        raise SystemExit(f"{path}: no team columns under the label row")

    best: dict[str, tuple[float, str]] = {}
    for row in sorted(by_row):
        if row <= header_row:
            continue
        cells_here = by_row[row]
        name = cells_here.get("A", "").strip()
        # The sheet stacks two tables: the validated scores first, then a table
        # of the same instances holding each team's *placement*. A bare "Rank"
        # in the label column separates them, and the placements must not be
        # mistaken for costs -- they are the same shape and a much smaller
        # number, so reading past this point silently reports a rank as a score.
        if name.lower() in {"rank", "average"} or name.lower().startswith("rank based"):
            break
        match = TUPLE.match(name)
        if not match:
            continue
        scores: list[tuple[float, str]] = []
        for col, team in teams.items():
            raw = cells_here.get(col, "")
            if not raw or raw == "-":
                continue
            try:
                scores.append((float(raw), team))
            except ValueError:
                continue
        if not scores:
            continue
        value, team = min(scores)
        if value <= 0:
            # Validation rejected every submission for this tuple.
            continue
        best[name] = (value, team)
    if not best:
        raise SystemExit(f"{path}: no validated scores were found")
    return best


def shipped(instance: str, history: str, weeks: list[str]) -> bool:
    """The tuple must resolve against the corpus we actually ship."""
    directory = EMPLOYEE_DIR / instance
    if not directory.is_dir():
        return False
    needed = [directory / f"H0-{instance}-{history}.txt"]
    needed += [directory / f"WD-{instance}-{week}.txt" for week in weeks]
    return all(path.exists() for path in needed)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args(argv)

    published = parse_validated_results(args.workbook)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    added, skipped, updated = [], [], []
    for name, (value, team) in sorted(published.items()):
        match = TUPLE.match(name)
        instance, history, weeks = (
            match.group("instance"),
            match.group("history"),
            match.group("weeks").split("-"),
        )
        if not shipped(instance, history, weeks):
            skipped.append(name)
            continue
        entry = {
            "reference": float(value),
            "status": "open",
            "lower_bound": None,
            "upper_bound": float(value),
            "reference_detail": f"best validated finalist result ({team})",
        }
        if name in catalog["instances"]:
            if catalog["instances"][name].get("reference") != float(value):
                updated.append(name)
            catalog["instances"][name] = entry
        else:
            catalog["instances"][name] = entry
            added.append(name)

    if not args.check:
        CATALOG.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(f"published tuples parsed : {len(published)}")
    print(f"added to the catalog    : {len(added)}")
    print(f"already present         : {len(published) - len(added) - len(skipped)}")
    print(f"skipped (no corpus file): {len(skipped)}")
    if skipped:
        for name in skipped:
            print(f"   {name}")
    if updated:
        print(f"values changed          : {len(updated)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
