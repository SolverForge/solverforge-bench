#!/usr/bin/env python3
"""Render the thread-study CSVs as a markdown comparison against 1 thread."""

from __future__ import annotations

import argparse
from pathlib import Path

from solverforge_bench.thread_study import read_study_runs, render_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="+", type=Path, help="Benchmark result CSVs.")
    parser.add_argument("--output", type=Path, help="Write the report here too.")
    args = parser.parse_args()
    report = render_report(read_study_runs(args.csv))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
