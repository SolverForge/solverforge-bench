# solverforge-bench

This repository is the official benchmark surface for SolverForge comparison work.
It groups benchmarks by SolverForge solve shape and runs every problem through
one shared framework: the framework owns the CLI, benchmark registry, run
matrix, timing, overshoot calculation, watchdog containment, result rows, and
CSV writing. Problem packages are adapters: they load/select cases, create
solver callables, validate/evaluate returned solutions, and expose native fields.

## Benchmarks

- `list-variable/cvrp/` is the canonical CVRP comparison imported from
  `~/hack/cvrp_solver_comparison`. It compares commercially usable Python solver
  integrations plus the retained SolverForge list-variable runtime.
- `scalar-variable/employee-scheduling/` is the nurse rostering benchmark. It
  uses the bundled INRC-II TXT corpus and compares `solverforge`,
  `timefold_java`, and `ortools` on nurse-to-shift assignments.

## Setup

Install dependencies into the CVRP virtualenv:

```sh
cd list-variable/cvrp
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ../..
cd ../..
```

## CVRP Commands

Run CVRP validation and smoke benchmarks from the repository root:

```sh
make validate-cvrp
make bench-cvrp-quick
make bench-cvrp-solverforge-quick
```

Run the full CVRP benchmark:

```sh
make bench-cvrp
```

The full CVRP path builds the Timefold Java fat JAR and the local
`solverforge_cvrp` Python extension before running the shared benchmark harness.
Generated CSV files are benchmark evidence artifacts; commit them only when they
are intentional result records.

The CVRP benchmark code under `list-variable/cvrp/` intentionally tracks the
source checkout at `~/hack/cvrp_solver_comparison`. Keep CVRP solver behavior
source-identical there; put cross-category reporting, database-loading behavior,
and shared execution policy at the repository level instead.

## Employee Scheduling Commands

Run local INRC-II reference validation:

```sh
make validate-employee-scheduling
make validate-employee-model-parity
```

`validate-employee-model-parity` is not a benchmark run. It checks that the
employee-scheduling adapters encode the same mathematical model contract:
optimal/minimum coverage slot generation, hard feasibility clauses, candidate
domains, and soft objective weights. It also re-validates bundled reference
solution costs through the shared Python validator.

Build employee-scheduling native integrations without running a benchmark:

```sh
make build-employee-scheduling
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

## Unified Harness

The root entrypoint runs the shared framework with problem-specific specs:

```sh
PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src \
  python3.12 scripts/run_benchmark.py cvrp --run-kind quick --num-instances 3 --time-limits 1 10

PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src \
  python3.12 scripts/run_benchmark.py employee-scheduling --run-kind quick --datasets n005w4 --time-limits 1 10
```

The benchmark budget and watchdog are separate. The requested time limit is
passed to the solver and measured with wall-clock timing around
`solver(instance, time_limit)`. If the solver returns after the nominal budget
but before the watchdog, the framework preserves the solution, validates it,
records `actual_time_seconds`, and reports overshoot:

```text
overshoot_seconds = max(0, actual_time_seconds - time_limit_seconds)
overshoot_ratio = overshoot_seconds / time_limit_seconds
wall_time_over_limit = actual_time_seconds > time_limit_seconds * 1.1
```

The watchdog exists only for runaway containment. By default it is
`max(time_limit * 1.25, time_limit + 5)`, configurable with
`--watchdog-multiplier` and `--watchdog-grace-seconds`. Only watchdog-killed
invocations lose the returned solution because the child process was forcibly
terminated.

## PostgreSQL Results

PostgreSQL persistence uses plain SQL migrations in `migrations/` with
SQLx-compatible file naming. SQLx is the Rust-side migration convention here
because it keeps schema changes as checked-in SQL, supports `sqlx migrate run`,
and can embed the same migrations in Rust code with `sqlx::migrate!()` when a
Rust service owns startup.

The local default database URL is:

```sh
postgresql://postgres@localhost/solverforge_bench
```

Prepare the database and apply migrations:

```sh
make db-check
make db-create
make db-migrate
```

`db-migrate` requires `sqlx-cli` on `PATH`:

```sh
cargo install sqlx-cli --no-default-features --features postgres
```

Save a benchmark run to PostgreSQL while still writing the normal CSV:

```sh
PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src \
  python3.12 scripts/run_benchmark.py cvrp \
    --run-kind quick \
    --num-instances 3 \
    --time-limits 1 10 \
    --save-postgres
```

Run kinds are:

```text
quick      smoke-scale runs
candidate  candidate comparison runs before release tagging
tag        SolverForge release snapshots, requires --release-tag
```

Use `BENCH_ARGS` to pass database options through Make targets:

```sh
make bench-cvrp-quick BENCH_ARGS="--save-postgres"
make bench-cvrp BENCH_ARGS="--run-kind tag --release-tag v0.11.1 --save-postgres"
```

## Result Schema

Benchmark runs now write one global snake_case CSV schema directly. Native
problem fields are stable optional columns, for example `nurses`, `weeks`,
`validator_model_delta`, and `score_drift`.

PostgreSQL stores run-level catalog data in `benchmark_runs` and one row per
solver/case/time-limit result in `benchmark_results`. Core benchmark columns are
typed columns. Benchmark-specific native fields are preserved in
`native_fields`, and the complete emitted row is preserved in `row_payload`.
Runs are catalogued as `running`, `completed`, or `failed`; interrupted runs keep
their partial rows but are excluded from latest-run display views.
Warehouse/display consumers can read `benchmark_result_facts`,
`latest_benchmark_runs`, or `latest_benchmark_result_facts` instead of
reconstructing the run/result join themselves.

For database loading or older native CSVs, `scripts/normalize_results.py` still
normalizes generated files:

```sh
make normalize-results INPUT=path/to/native.csv OUTPUT=results/normalized.csv
make normalize-results INPUT=path/to/native.csv OUTPUT=results/normalized.ndjson ARGS="--format ndjson"
```

The normalized rows use these columns:

```text
run_id, benchmark_name, benchmark_category, dataset, dataset_set, instance,
instance_size, solver, time_limit_seconds, actual_time_seconds,
overshoot_seconds, overshoot_ratio, wall_time_over_limit,
watchdog_limit_seconds, watchdog_killed, run_error, hard_feasible, cost,
reported_cost, fresh_cost, reference_cost, quality_ratio, validation_error,
solution_artifact, nurses, weeks, validator_model_delta, score_drift,
source_file
```
