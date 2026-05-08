# solverforge-bench

This repository is the official benchmark surface for SolverForge comparison work.
It groups benchmarks by SolverForge solve shape and keeps each problem kind close
to its source-of-truth implementation.

## Benchmarks

- `list-variable/cvrp/` is the canonical CVRP comparison imported from
  `~/hack/cvrp_solver_comparison`. It compares commercially usable Python solver
  integrations plus the retained SolverForge list-variable runtime.
- `scalar-variable/employee-scheduling/` is the nurse rostering benchmark. It
  uses the bundled INRC-II TXT corpus and compares `solverforge`,
  `timefold_java`, and `ortools` on nurse-to-shift assignments.

## CVRP Commands

Install dependencies into the CVRP virtualenv used by the copied source-truth
scripts:

```sh
cd list-variable/cvrp
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ../..
cd ../..
```

Run CVRP validation and smoke benchmarks from the repository root:

```sh
make validate-cvrp
make bench-cvrp-quick
make bench-solverforge-quick
```

Run the full CVRP benchmark:

```sh
make bench-cvrp
```

The full CVRP path builds the Timefold Java fat JAR and the local
`solverforge_cvrp` Python extension before running `scripts/run_benchmark.py`.
Generated CSV files are benchmark evidence artifacts; commit them only when they
are intentional result records.

The CVRP benchmark code under `list-variable/cvrp/` intentionally tracks the
source checkout at `~/hack/cvrp_solver_comparison`. Keep CVRP solver behavior
source-identical there; put cross-category reporting or database-loading
behavior at the repository level instead.

## Employee Scheduling Commands

Build the employee-scheduling SolverForge extension and Timefold Java adapter:

```sh
make -C scalar-variable/employee-scheduling build
```

Run local INRC-II reference validation:

```sh
make validate-employee-scheduling
```

Run the quick and canonical employee-scheduling benchmarks:

```sh
make bench-employee-scheduling-quick
make bench-employee-scheduling
```

The quick target runs `n005w4` for `solverforge`, `timefold_java`, and `ortools`
at `1` and `10` seconds.
The canonical target uses the `canonical` group in
`scalar-variable/employee-scheduling/data/inrc2/manifest.json`.

## Result Normalization

Benchmark runners keep their native output close to each problem family. For
database loading, normalize any generated CVRP or employee-scheduling CSV into a
stable snake_case schema:

```sh
make normalize-results INPUT=path/to/native.csv OUTPUT=results/normalized.csv
make normalize-results INPUT=path/to/native.csv OUTPUT=results/normalized.ndjson ARGS="--format ndjson"
```

The normalized rows use these columns:

```text
run_id, benchmark_category, benchmark_name, dataset, dataset_set, instance,
instance_size, nurses, weeks, solver, time_limit_seconds, actual_time_seconds,
hard_feasible, cost, reference_cost, quality_ratio, validation_error, source_file
```
