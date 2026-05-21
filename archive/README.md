# Archived Benchmark Material

This directory contains historical reports and older standalone benchmark
scripts. It is not the active benchmark surface.

Active benchmark execution lives at the repository root:

```sh
make install-python-deps
make bench-cvrp-quick
make bench-employee-scheduling-quick
PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src \
  .venv/bin/python3 scripts/run_benchmark.py --config benchmark.example.toml
```

The current framework owns CLI parsing, TOML configuration, run matrix
construction, timing, overshoot calculation, watchdog containment, CSV writing,
and optional PostgreSQL persistence from `src/solverforge_bench/`. See the root
`README.md` for supported commands and schema details, and `WIREFRAME.md` for
the current as-built repository map.

Files in `archive/` may describe older server-based experiments, older report
formats, or deprecated quickstart paths. Do not use them as implementation
guidance for current CVRP or employee-scheduling benchmark work.
