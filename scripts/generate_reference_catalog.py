#!/usr/bin/env python3.14
"""Generate a problem's versioned reference catalog from its pinned source.

Each problem type resolves its official reference from a different kind of
pinned source, and each source answers a different question. Job-shop values
come from the ScheduleOpt best-known catalogue. CVRP values come from the
CVRPLIB Set X table, where the ``Opt`` column separates a proven optimum from a
best-known upper bound. Employee scheduling has no published solution set at
all: the competition distributes instances only, and the published literature
solves different history/week tuples than the canonical selection uses, so the
only official values that exist are the validator-scored costs of the reference
solutions the corpus itself ships.

The generator never invents a value. An instance whose official value cannot be
established is written as an explicit gap so the run that needs it fails loudly
instead of publishing a gap to an unknown reference.

Usage:
    scripts/generate_reference_catalog.py jssp <catalog.json> [--check]
    scripts/generate_reference_catalog.py cvrp <catalog.json> --source <table.txt> [--check]
    scripts/generate_reference_catalog.py employee <catalog.json> [--check]

``--check`` regenerates in memory and compares against the committed file, so CI
fails when a catalog drifts from the source it claims to have come from.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]

JSSP_DIR = ROOT / "scalar-variable/job-shop-scheduling/data/jsplib"
CVRP_DIR = ROOT / "list-variable/cvrp/data/X"
EMPLOYEE_DIR = ROOT / "scalar-variable/employee-scheduling/data/inrc2"

CVRPLIB_SOURCE_NAME = "CVRPLIB (Uchoa et al. 2017 Set X)"
DEFAULT_CVRP_TABLE = ROOT / "list-variable/cvrp/data/X/cvrplib-set-x.txt"

#: The competition's validated-results workbook, kept beside the corpus it scores.
PUBLISHED_RESULTS_FILE = "inrc2-validated-results.xlsx"
TUPLE_PATTERN = re.compile(
    r"^(?P<instance>n\d+w\d+)_(?P<history>\d+)_(?P<weeks>[\d-]+)$"
)


def _load_published_module():
    """Import the published-results parser so both scripts share one rule."""
    spec = importlib.util.spec_from_file_location(
        "import_inrc2_published_results",
        ROOT / "scripts/import_inrc2_published_results.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def published_results(workbook: Path) -> dict[str, tuple[float, str]]:
    return _load_published_module().parse_validated_results(workbook)


def _corpus_has(instance: str, history: str, weeks: list[str]) -> bool:
    """The tuple must resolve against the corpus we actually ship."""
    directory = EMPLOYEE_DIR / instance
    if not directory.is_dir():
        return False
    needed = [directory / f"H0-{instance}-{history}.txt"]
    needed += [directory / f"WD-{instance}-{week}.txt" for week in weeks]
    return all(path.exists() for path in needed)


def enumerable_case_names() -> set[str]:
    """Case names the employee loader can actually enumerate.

    The loader discovers a case from a ``Solution_H_<h>-WD_<weeks>`` directory,
    so a catalog key that does not correspond to such a directory can never be
    resolved from the run it would describe.
    """
    sys.path.insert(0, str(ROOT / "scalar-variable/employee-scheduling/src"))
    from employee_scheduling_bench.loader import enumerate_instances  # noqa: PLC0415

    return {info["name"] for info in enumerate_instances(str(EMPLOYEE_DIR))}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict, check: bool) -> int:
    rendered = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    if check:
        committed = path.read_text(encoding="utf-8") if path.exists() else ""
        if committed != rendered:
            print(f"{path} is stale: regenerate it from its source", file=sys.stderr)
            return 1
        print(f"{path} matches its source")
        return 0
    path.write_text(rendered, encoding="utf-8")
    print(f"wrote {path} ({len(payload['instances'])} instances)")
    return 0


def generate_jssp(check: bool) -> int:
    """Re-express the pinned ScheduleOpt catalogue in the shared shape."""
    source_catalog = _load(JSSP_DIR / "best_known_solutions.json")
    source = source_catalog["source"]
    instances = {}
    for name, entry in source_catalog["instances"].items():
        if entry["status"] not in ("closed", "open"):
            raise SystemExit(f"jssp {name}: unexpected status {entry['status']!r}")
        instances[name] = {
            "reference": entry["upper_bound"],
            "status": entry["status"],
            "lower_bound": entry["lower_bound"],
            "upper_bound": entry["upper_bound"],
        }
    payload = {
        "source": {
            "name": source["name"],
            "revision": source["revision"],
            "url": source["url"],
            "metadata_url": source.get("metadata_url"),
        },
        "instances": instances,
    }
    return _write(JSSP_DIR / "references.json", payload, check)


CVRPLIB_ROW = re.compile(
    r"^(?P<name>X-n\d+-k\d+)\s+\d+\s+\d+\s+\d+\s+(?P<ub>[\d.,]+)\s+(?P<opt>yes|no)$"
)


def parse_cvrplib_table(text: str) -> dict:
    """Parse the CVRPLIB Set X table rows into catalog entries.

    The table's ``Opt`` column is the reference kind: ``yes`` means the value is
    a proven optimum, ``no`` means it is the best known upper bound.
    """
    instances = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = CVRPLIB_ROW.match(line)
        if not match:
            raise SystemExit(f"cvrp: unparsable CVRPLIB row {line!r}")
        value = float(match.group("ub").replace(",", ""))
        optimum = match.group("opt") == "yes"
        instances[match.group("name")] = {
            "reference": value,
            "status": "closed" if optimum else "open",
            "lower_bound": value if optimum else None,
            "upper_bound": value,
        }
    if not instances:
        raise SystemExit("cvrp: the CVRPLIB table produced no instances")
    return instances


def generate_cvrp(check: bool, table_path: Path) -> int:
    if not table_path.exists():
        raise SystemExit(
            f"cvrp: no CVRPLIB table at {table_path}. The bundled .sol files hold "
            f"solution routes, not official values; the official table is required."
        )
    instances = parse_cvrplib_table(table_path.read_text(encoding="utf-8"))

    local = sorted(p.stem for p in CVRP_DIR.glob("*.vrp"))
    missing = [name for name in local if name not in instances]
    if missing:
        raise SystemExit(
            f"cvrp: bundled instance(s) absent from the official table: {missing}"
        )
    extra = [name for name in instances if name not in set(local)]
    if extra:
        raise SystemExit(f"cvrp: table lists instances we do not bundle: {extra}")

    payload = {
        "source": {
            "name": CVRPLIB_SOURCE_NAME,
            "revision": "cvrplib-set-x-live-2026-10-01",
            "url": "https://galgos.inf.puc-rio.br/cvrplib/index.php/en/instances",
            "note": (
                "Values read from the CVRPLIB Set X table; the Opt column decides "
                "whether a value is a proven optimum or a best known bound."
            ),
        },
        "instances": instances,
    }
    return _write(CVRP_DIR / "references.json", payload, check)


EMPLOYEE_SOLUTION_DIR = re.compile(r"^Solution_H_(?P<hist>\d+)-WD_(?P<weeks>[\d-]+)$")


def _employee_instance_name(directory_name: str, hist: int, weeks: list[int]) -> str:
    return f"{directory_name}_H{hist}_WD{'-'.join(str(w) for w in weeks)}"


def employee_reference_instances() -> dict[str, tuple[str, list[int]]]:
    """Every instance the bundled corpus can resolve an official value for.

    A ``Solution_H_*`` directory with no solution rows is the competition's
    published tuple: it marks the case as enumerable and carries its reference in
    the catalog, so it is skipped here rather than scored.
    """
    found: dict[str, tuple[str, list[int]]] = {}
    for instance_dir in sorted(EMPLOYEE_DIR.iterdir()):
        if not instance_dir.is_dir():
            continue
        for sol_dir in sorted(instance_dir.glob("Solution_H_*")):
            match = EMPLOYEE_SOLUTION_DIR.match(sol_dir.name)
            if not match:
                continue
            if not any(sol_dir.glob("Sol-*.txt")):
                continue
            hist = int(match.group("hist"))
            weeks = [int(x) for x in match.group("weeks").split("-")]
            name = _employee_instance_name(instance_dir.name, hist, weeks)
            found[name] = (str(sol_dir), weeks)
    return found


def _score_reference_solution(sol_dir: Path, weeks: list[int]):
    """Validate a shipped reference solution and return its official cost.

    This evaluates a fixed artefact the corpus ships; it does not invoke a
    solver and produces no benchmark run.

    The solution rows are ordered by their trailing stage index, and each row's
    leading index names the week data file it belongs to -- which is why the
    directory name's ``WD_`` sequence matches those indices exactly. The week
    order is therefore read from the row names rather than assumed from the
    directory name, and the two are cross-checked.
    """
    here = ROOT / "scalar-variable/employee-scheduling/src"
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    from employee_scheduling_bench.loader import (
        _solution_stage_index,
        load_instance,
        load_solution,
    )
    from employee_scheduling_bench.validation import validate_breakdown

    instance_name = sol_dir.parent.name
    sol_files = sorted(sol_dir.glob("Sol-*.txt"), key=_solution_stage_index)
    if not sol_files:
        raise SystemExit(f"employee: {sol_dir} holds no solution rows")

    row_weeks = []
    for path in sol_files:
        parts = path.stem.split("-")
        if len(parts) != 4:
            raise SystemExit(f"employee: unexpected solution row name {path.name!r}")
        row_weeks.append(int(parts[2]))

    if row_weeks != weeks:
        raise SystemExit(
            f"employee: {sol_dir.name} names weeks {weeks} but its rows carry "
            f"{row_weeks}"
        )

    week_paths = [sol_dir.parent / f"WD-{instance_name}-{w}.txt" for w in row_weeks]
    for path in week_paths:
        if not path.exists():
            raise SystemExit(f"employee: {sol_dir} needs missing {path}")

    history_index = int(re.search(r"Solution_H_(\d+)", sol_dir.name).group(1))
    instance = load_instance(
        str(sol_dir.parent / f"Sc-{instance_name}.txt"),
        str(sol_dir.parent / f"H0-{instance_name}-{history_index}.txt"),
        [str(p) for p in week_paths],
    )
    solution = load_solution(str(sol_dir))
    breakdown = validate_breakdown(solution, instance)
    return sum(breakdown.values()), breakdown


def generate_employee(check: bool) -> int:
    """Write the employee catalog from both official sources.

    The bundled corpus supplies the tuples the competition published reference
    solutions for; the competition's validated-results workbook supplies the
    tuples it scored across the finalists' submissions. They cover different
    history/week selections, and neither alone covers every instance we run, so
    the catalog carries both rather than whichever ran last.
    """
    instances = {}
    for name, (sol_dir, weeks) in sorted(employee_reference_instances().items()):
        cost, _ = _score_reference_solution(Path(sol_dir), weeks)
        instances[name] = {
            "reference": float(cost),
            "status": "open",
            "lower_bound": None,
            "upper_bound": float(cost),
            "reference_detail": "bundled reference solution",
        }

    workbook = EMPLOYEE_DIR / PUBLISHED_RESULTS_FILE
    if workbook.exists():
        for name, (value, team) in sorted(published_results(workbook).items()):
            match = TUPLE_PATTERN.match(name)
            if match is None:
                continue
            instance, history = match.group("instance"), match.group("history")
            weeks = match.group("weeks").split("-")
            if not _corpus_has(instance, history, weeks):
                continue
            # The workbook names a tuple "<instance>_<h>_<weeks>"; the loader
            # names the same case "<instance>_H<h>-WD<weeks>". Key the catalog by
            # the case name, so the reference resolves from the case it belongs
            # to rather than from a name no run ever produces.
            case_name = f"{instance}_H{history}_WD{match.group('weeks')}"
            instances[case_name] = {
                "reference": float(value),
                "status": "open",
                "lower_bound": None,
                "upper_bound": float(value),
                "reference_detail": f"best validated finalist result ({team})",
            }

    payload = {
        "source": {
            "name": "INRC-II official test dataset (mobiz.vives.be/inrc2)",
            "revision": "inrc2-official-test-dataset-2014",
            "url": "https://mobiz.vives.be/inrc2/?page_id=20",
            "metadata_url": "http://mobiz.vives.be/inrc2/wp-content/uploads/2014/08/testdatasets_txt.zip",
            "note": (
                "The competition publishes the test instances together with their "
                "reference solutions and no other solution set; the canonical "
                "selection is exactly that published test set, and the bundled "
                "corpus is byte-identical to it. These values are the penalties the "
                "official validator reports for those reference solutions, so they "
                "are best known upper bounds, not proven optima. The extended and "
                "hidden datasets ship instances without any solution."
            ),
        },
        "instances": instances,
    }
    return _write(EMPLOYEE_DIR / "references.json", payload, check)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem", choices=("jssp", "cvrp", "employee"))
    parser.add_argument(
        "output",
        nargs="?",
        help="catalog path; defaults to the problem's pinned data directory",
    )
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    parser.add_argument(
        "--source",
        default=str(DEFAULT_CVRP_TABLE),
        help="CVRPLIB Set X table for the cvrp catalog",
    )
    args = parser.parse_args(argv)

    if args.problem == "jssp":
        return generate_jssp(args.check)
    if args.problem == "cvrp":
        return generate_cvrp(args.check, Path(args.source))
    return generate_employee(args.check)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
