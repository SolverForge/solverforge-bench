#!/usr/bin/env python3
"""Refresh the pinned official reference sources from upstream.

Each reference catalog is generated from a source file committed beside the
instances. This script re-reads those sources from where they are published,
rewrites the committed source files only when a value the benchmark uses has
changed, and regenerates the affected catalogs. The result is an ordinary diff
for review: nothing reaches a run or the warehouse until it is merged.

    scripts/refresh_reference_sources.py [--problem jssp|cvrp|all] [--check]
                                         [--summary PATH]

Sources:

    jssp      ScheduleOpt/benchmarks ``jobshop/solutions/bks.json`` at the head
              of its default branch; the revision is that commit.
    cvrp      The CVRPLIB Set X table on the CVRPLIB instances page; the
              revision is the retrieval date of a table that changed.
    employee  The INRC-II competition closed in 2014 and its published values
              are frozen, so there is nothing to refresh.

``--check`` reports differences without writing and exits 1 when upstream has
moved. ``--summary`` writes a Markdown summary of the changes (for a pull
request body). Standard library only, so it runs on a bare CI image.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
JSSP_DIR = ROOT / "scalar-variable/job-shop-scheduling/data/jsplib"
CVRP_DIR = ROOT / "list-variable/cvrp/data/X"

JSSP_SOURCE_FILE = JSSP_DIR / "best_known_solutions.json"
JSSP_REPO = "ScheduleOpt/benchmarks"
JSSP_HEAD_URL = f"https://api.github.com/repos/{JSSP_REPO}/commits/HEAD"
JSSP_BKS_URL = (
    "https://raw.githubusercontent.com/"
    + JSSP_REPO
    + "/{revision}/jobshop/solutions/bks.json"
)

CVRP_TABLE = CVRP_DIR / "cvrplib-set-x.txt"
CVRP_TABLE_SOURCE = CVRP_DIR / "cvrplib-set-x.source.json"
CVRP_PAGE_URL = "https://galgos.inf.puc-rio.br/cvrplib/index.php/en/instances"

USER_AGENT = "solverforge-bench reference refresh"


def fetch(url: str, *, attempts: int = 4) -> bytes:
    """GET with retries: upstream hosts and this network both flap."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except OSError as exc:
            last = exc
            time.sleep(5 * (attempt + 1))
    raise SystemExit(f"could not fetch {url}: {last}")


def _number(value):
    """Upstream writes integral bounds as integers; keep them that way."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# --- job-shop -----------------------------------------------------------------


def refresh_jssp(check: bool) -> list[str]:
    pinned = json.loads(JSSP_SOURCE_FILE.read_text(encoding="utf-8"))
    head = json.loads(fetch(JSSP_HEAD_URL))
    revision = head["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SystemExit(f"jssp: unexpected upstream revision {revision!r}")
    upstream_entries = json.loads(fetch(JSSP_BKS_URL.format(revision=revision)))
    upstream = {entry["instance"]: entry for entry in upstream_entries}

    changes: list[str] = []
    instances = {}
    for name, entry in pinned["instances"].items():
        source = upstream.get(entry["source_instance"])
        if source is None:
            raise SystemExit(
                f"jssp: {name} ({entry['source_instance']}) is missing upstream at "
                f"{revision}; refusing to drop a reference silently"
            )
        if source["status"] not in ("closed", "open"):
            raise SystemExit(f"jssp: {name} has upstream status {source['status']!r}")
        refreshed = {
            "source_instance": entry["source_instance"],
            "status": source["status"],
            "lower_bound": _number(source["lower_bound"]),
            "upper_bound": _number(source["upper_bound"]),
        }
        for field in ("status", "lower_bound", "upper_bound"):
            if refreshed[field] != entry[field]:
                changes.append(
                    f"jssp `{name}` {field}: {entry[field]} -> {refreshed[field]}"
                )
        instances[name] = refreshed

    if not changes:
        print(f"jssp: no value changed (upstream {revision})")
        return []
    print(f"jssp: {len(changes)} change(s) at upstream {revision}")
    if not check:
        payload = {
            "source": {
                **pinned["source"],
                "revision": revision,
                "metadata_url": JSSP_BKS_URL.format(revision=revision),
            },
            "instances": instances,
        }
        JSSP_SOURCE_FILE.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    return [f"ScheduleOpt revision `{revision}`"] + changes


# --- CVRP ---------------------------------------------------------------------

_ROW = re.compile(r"<tr\b[^>]*\bid=\"set-\d+\"[^>]*>(?P<body>.*?)</tr>", re.S)
_CELL = re.compile(r"<td\b[^>]*>(?P<cell>.*?)</td>", re.S)
_TAG = re.compile(r"<[^>]+>|<!--.*?-->", re.S)


def _cell_text(cell: str) -> str:
    text = html.unescape(_TAG.sub(" ", cell))
    text = text.replace("{,}", ",").replace("$", "")
    return " ".join(text.split())


def parse_cvrplib_page(page: str) -> dict[str, str]:
    """Set X rows of the CVRPLIB instances page, rendered as table lines."""
    rows: dict[str, str] = {}
    for match in _ROW.finditer(page):
        cells = [_cell_text(c.group("cell")) for c in _CELL.finditer(match["body"])]
        if len(cells) < 6 or not re.fullmatch(r"X-n\d+-k\d+", cells[0]):
            continue
        name, n, k, capacity, upper, optimum = cells[:6]
        optimum = optimum.lower()
        if optimum not in ("yes", "no"):
            raise SystemExit(f"cvrp: {name} has Opt column {optimum!r}")
        value = float(upper.replace(",", ""))
        rows[name] = f"{name} {n} {k} {capacity} {value:,.2f} {optimum}"
    if not rows:
        raise SystemExit("cvrp: the CVRPLIB page carried no Set X rows")
    return rows


def refresh_cvrp(check: bool) -> list[str]:
    committed_lines = [
        line for line in CVRP_TABLE.read_text(encoding="utf-8").splitlines() if line
    ]
    committed = {line.split()[0]: line for line in committed_lines}
    upstream = parse_cvrplib_page(fetch(CVRP_PAGE_URL).decode("utf-8", "replace"))

    missing = sorted(set(committed) - set(upstream))
    if missing:
        raise SystemExit(f"cvrp: bundled instance(s) missing upstream: {missing}")
    changes = [
        f"cvrp `{name}`: `{committed[name]}` -> `{upstream[name]}`"
        for name in committed
        if upstream[name] != committed[name]
    ]
    if not changes:
        print("cvrp: no value changed")
        return []
    retrieved = dt.date.today().isoformat()
    print(f"cvrp: {len(changes)} change(s) on {retrieved}")
    if not check:
        CVRP_TABLE.write_text(
            "\n".join(upstream[name] for name in committed) + "\n", encoding="utf-8"
        )
        source = json.loads(CVRP_TABLE_SOURCE.read_text(encoding="utf-8"))
        source["revision"] = f"cvrplib-set-x-live-{retrieved}"
        source["retrieved"] = retrieved
        CVRP_TABLE_SOURCE.write_text(
            json.dumps(source, indent=2) + "\n", encoding="utf-8"
        )
    return [f"CVRPLIB table retrieved {retrieved}"] + changes


# --- driver -------------------------------------------------------------------

REFRESHERS = {"jssp": refresh_jssp, "cvrp": refresh_cvrp}


def regenerate(problem: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate_reference_catalog.py"), problem],
        check=True,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem", choices=("all", *REFRESHERS), default="all")
    parser.add_argument("--check", action="store_true", help="report, do not write")
    parser.add_argument("--summary", type=Path, help="write a Markdown change summary")
    args = parser.parse_args(argv)

    problems = list(REFRESHERS) if args.problem == "all" else [args.problem]
    print("employee: INRC-II values are frozen since 2014; nothing to refresh")
    report: dict[str, list[str]] = {}
    for problem in problems:
        changes = REFRESHERS[problem](args.check)
        if changes:
            report[problem] = changes
            if not args.check:
                regenerate(problem)

    if args.summary is not None:
        lines = ["Official reference sources moved upstream.", ""]
        for problem, changes in report.items():
            lines.append(f"### {problem}")
            lines.extend(f"- {change}" for change in changes)
            lines.append("")
        lines.append(
            "Merging changes the reference every later run is graded against; "
            "runs already recorded keep the catalog version they were pinned to."
        )
        args.summary.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.check and report:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
