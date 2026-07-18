# solverforge-bench

This repository is the official benchmark surface for SolverForge comparison work.
It groups benchmarks by SolverForge solve shape and runs every problem through
one shared framework: the framework owns the CLI, TOML configuration, benchmark
registry, run matrix, timing, overshoot calculation, watchdog containment,
result rows, CSV writing, production logging, solver stdout/stderr capture, and
optional PostgreSQL persistence. Problem packages are adapters: they load/select
cases, create solver callables, validate/evaluate returned solutions, and expose
native fields.
See `WIREFRAME.md` for the current as-built repository map.

## Benchmarks

- `list-variable/cvrp/` is the canonical CVRP comparison imported from
  `~/hack/cvrp_solver_comparison`. It compares commercially usable Python solver
  integrations, native VROOM, rustvrp, Timefold, and the SolverForge CVRP
  list-variable runtime. `solverforge` is the native Rust/PyO3 adapter and
  `solverforge-py` is the public Python-binding model path.
- `scalar-variable/employee-scheduling/` is the nurse rostering benchmark. It
  uses the bundled INRC-II TXT corpus and compares `solverforge`,
  `solverforge-py`, `timefold`, and `ortools` on nurse-to-shift assignments.
  The Python-binding path is a first-class default row for public scalar
  assignment-group coverage.
- `scalar-variable/job-shop-scheduling/` is the job-shop scheduling benchmark. It
  uses the bundled classic JSPLIB corpus for machine scheduling with job
  precedence and disjunctive machine capacity constraints. It compares
  `solverforge`, `solverforge-py`, `timefold`, and `ortools` on fixed-machine
  operation start times. The Python-binding path exercises list variables,
  owner hooks, precedence hooks, and the public first-class list
  precedence/makespan constraint as a default comparison row.
  The SolverForge adapter is a Rust/PyO3 planning model, the Timefold adapter
  is a Java fat JAR, and the OR-Tools adapter is a native C++ CP-SAT
  executable. The SolverForge adapter maps JSPLIB data into stock list
  variables and the upstream `ListPrecedenceMakespanConstraint`; it does not
  provide benchmark-local search helpers or warm-start schedules.

## Documentation Map

- `README.md` is the operator guide for setup, benchmark commands, configuration,
  persistence, and result schema.
- `AGENTS.md` is the maintainer and agent contract for scoped changes.
- `WIREFRAME.md` is the current as-built structure and data-flow map.
- `archive/README.md` marks archived reports and standalone scripts as
  historical material only.

## Setup

Create the repository virtualenv and install every benchmark dependency into it:

```sh
python3.14 -m venv .venv
. .venv/bin/activate
pip install -e .
```

The root Makefile uses this same `.venv` for CVRP, employee scheduling,
normalization, and nightly runs. `make install-python-deps` creates or refreshes
it before benchmark builds and is the CI-safe entrypoint for scripts that
bootstrap themselves through the repository virtualenv. That target installs
the exact published `solverforge==0.6.2` wheel into the same `.venv`, so
`solverforge-py` benchmark rows never depend on global Python packages or a
sibling checkout.

The CVRP, employee-scheduling, and job-shop SolverForge benchmark adapters are
aligned to the exact published SolverForge `0.19.0` crates and committed
registry lockfiles. The `solverforge-py` adapters use the exact published
`solverforge==0.6.2` distribution and report that distribution version in CSV
and PostgreSQL rows.

Each workload keeps two separate SolverForge configuration artifacts: the
native adapter's `solver.toml` and the Python adapter's `solverforge_py.toml`.
The files must parse to the same policy. CVRP uses the full qualified
construction and seven-neighborhood local-search policy. Employee scheduling
and JSSP intentionally leave phases unspecified so both bindings select the
same model-aware SolverForge defaults. At runtime, both adapters change only
the requested termination seconds. `make verify-solverforge-config-parity`
rejects semantic drift and also rejects replacing both files with an equally
weaker policy.

Benchmark run targets execute the shared harness through `taskset` with
different default pinned cores: `CVRP_BENCH_CPU ?= 0`,
`EMPLOYEE_BENCH_CPU ?= 1`, and `JOBSHOP_BENCH_CPU ?= 2`. They set
`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, and a per-core `BENCH_LOCK`; runs on
different cores can proceed in parallel, while accidental same-core runs
serialize. Set `BENCH_CPU=<n>` to intentionally force all suites onto one core.

## Fair-Start Contract

Solver adapters receive only the problem instance and the benchmark time limit.
Scalar-variable models must start from unassigned planning variables, and
list-variable models must start from empty lists. Adapter-owned incumbents,
hints, hard seeds, fallback schedules, warm starts, and reference-solution reads
are not valid benchmark inputs.

Every solver wrapper returns a `SolverResult` with a runtime fair-start witness.
The harness validates that witness in the child process, records
`fair_start_valid`, `fair_start_error`, and `fair_start_witness` in CSV and
PostgreSQL rows, and aborts the run if a solver reaches the execution boundary
without a clean witness. Native adapters also report solver-specific checks,
such as CP-SAT solution-hint counts for OR-Tools.

Reference solutions remain valid in specs, validators, parity scripts, demos,
and result evaluation because they are external scoring inputs, not solver
starts. Run `make verify-fair-start` after changing solver adapters, specs,
validators, CI, or benchmark architecture documentation. After a PostgreSQL
smoke run, use `make verify-fair-start-rows RUN_ID=<uuid>` to require every
persisted row in that run to carry a valid witness.

Use `make verify-stock-solverforge-guardrails` after upstream SolverForge
solver architecture changes. It builds the active native adapters, runs the
stock JSSP quick group plus a fixed JSPLIB canonical subset, and requires
SolverForge JSSP, CVRP, and employee smoke rows to stay hard-feasible with
valid fair-start witnesses. Add `--require-jssp-win` through `GUARDRAIL_ARGS`
when checking the final JSSP win condition.

## SolverForge-Py Adapter Test Gate

`solverforge-py` is part of the default quick, canonical, and nightly solver
sets for every benchmark class. Before release work, public benchmark claims,
or changes to the Python-binding solver paths, refresh the root `.venv` with
`make install-python-deps`; that target force-refreshes the exact published
`solverforge==0.6.2` wheel in the benchmark environment.

Run the local/release guardrails explicitly:

```sh
make verify-solverforge-config-parity
make verify-solverforge-py-guardrail-contract
make verify-solverforge-py-smoke
make verify-solverforge-py-comparison
make verify-solverforge-py-release
```

The configuration gate is a prerequisite of every native SolverForge build and
every native/Python guardrail. The guardrail-contract gate exercises exact
matrix coverage and secret-redaction regressions without running a solver. The
smoke gate remains a focused
`solverforge-py` adapter check for CVRP,
employee scheduling, and the JSSP quick group. The comparison gate runs paired
native `solverforge` and `solverforge-py` rows, resolves every requested dataset
selector before execution, requires every expected instance/time-limit/solver
row exactly once, validates fair-start and row integrity, and writes a
machine-readable summary under
`build/solverforge-py-guardrails/summary.json`. The release gate combines
compileall, validators, fair-start checks, native adapter builds, smoke, and
comparison into one release-mode guardrail invocation and summary.

The comparison gate does not bless a Python/native difference as expected.
Ratio thresholds are reported by default and become failures when an explicit
`--max-*-py-rust-ratio` is passed through
`SOLVERFORGE_PY_GUARDRAIL_ARGS`. Treat its single matrix as a compatibility and
quality guardrail, not as statistically qualified performance evidence.
PostgreSQL persistence is disabled by default; pass `--save-postgres` only when
you intentionally want warehouse rows. Database URLs are used for execution but
their command-argument values are redacted from guardrail summaries, failure
messages, and persisted benchmark run metadata.

## CI

`.github/workflows/ci.yml` defines the GitHub-hosted workflow, and
`.forgejo/workflows/ci.yml` defines the local Forgejo workflow. Forgejo reads
workflows from `.forgejo/workflows`, so its runner labels stay separate from
GitHub's `ubuntu-latest` jobs. The Python jobs set up Python 3.14, create the
root `.venv` with `make install-python-deps HOST_PYTHON=...`, compile the
source trees including job-shop scheduling, parse `benchmark*.toml`, run
`make verify-solverforge-py-guardrail-contract`, run `make verify-fair-start`,
run `make validate-cvrp`, and run
`make validate-employee-model-parity`. The parity script requires that root
`.venv`, so CI must use the Makefile bootstrap instead of a detached
`python -m pip install -e .`.

The Rust jobs resolve the exact SolverForge `0.19.0` crates from the committed
registry lockfiles. They set the PyO3 Python environment from
`actions/setup-python`, then run formatting,
`cargo clippy --locked --all-targets -- -D warnings`, and `cargo build --locked`
for the CVRP SolverForge adapter, CVRP rustvrp adapter, employee scheduling
SolverForge adapter, and job-shop scheduling SolverForge adapter. GitHub uses
the hosted setup actions; Forgejo uses the local `python` and `rust` runner
labels and installs Python 3.14 through a shell bootstrap before invoking the
same Makefile targets.

## CVRP Commands

Run CVRP validation and smoke benchmarks from the repository root:

```sh
make validate-cvrp
make bench-cvrp-quick
make bench-cvrp-solverforge-quick
make bench-cvrp-solverforge-quick-db
```

`bench-cvrp-quick` uses the full default CVRP solver set on three instances at
`1` and `10` seconds, including both native `solverforge` and
`solverforge-py`. The `bench-cvrp-solverforge-*` targets keep the
native-SolverForge-only development smoke path, with the `-db` variant applying
migrations and persisting the same run to PostgreSQL.

Run the full CVRP benchmark:

```sh
make bench-cvrp
```

The full CVRP path installs Python dependencies into the root `.venv`, builds
the Timefold fat JAR, builds native OR-Tools, VROOM, and rustvrp binaries, and
builds the local `solverforge_cvrp` Python extension into that same environment
before running the shared benchmark harness. Generated CSV files are benchmark
evidence artifacts; commit them only when they are intentional result records.

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
make bench-employee-scheduling-solverforge-quick
make bench-employee-scheduling-solverforge-quick-db
make bench-employee-scheduling
```

The quick target runs `n005w4` for `solverforge`, `solverforge-py`, `timefold`,
and `ortools` at `1` and `10` seconds. The SolverForge-only quick target runs
the same slice with only native `solverforge`, and the `-db` variant applies
migrations and persists the run.
The canonical target uses the `canonical` group in
`scalar-variable/employee-scheduling/data/inrc2/manifest.json`.

## Job-Shop Scheduling Commands

Run local JSPLIB parser and manifest validation:

```sh
make validate-job-shop-scheduling
```

Build all job-shop scheduling integrations without running a benchmark:

```sh
make build-job-shop-scheduling
```

Run the quick and canonical job-shop scheduling benchmarks:

```sh
make bench-job-shop-scheduling-quick
make bench-job-shop-scheduling
```

The quick target runs the JSPLIB `quick` group for `solverforge`,
`solverforge-py`, `timefold`, and `ortools` at `1` and `10` seconds. The
canonical target uses the `canonical` group in
`scalar-variable/job-shop-scheduling/data/jsplib/manifest.json`.
In the current bundled manifest, `quick` contains `ft06` and `la01`, while
`canonical` contains all 162 classic JSPLIB instances from `tamy0612/JSPLIB`
(`abz`, `ft`, `la`, `orb`, `swv`, `ta`, and `yn`). The manifest records the
upstream source URL and known optimum or lower/upper bounds when the upstream
metadata provides them.

## Unified Harness

The root entrypoint runs the shared framework with problem-specific specs:

```sh
PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src \
  .venv/bin/python3 scripts/run_benchmark.py cvrp --run-kind quick --num-instances 3 --time-limits 1 10

PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src \
  .venv/bin/python3 scripts/run_benchmark.py employee-scheduling --run-kind quick --datasets n005w4 --time-limits 1 10

PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src \
  .venv/bin/python3 scripts/run_benchmark.py job-shop-scheduling --run-kind quick --dataset-set quick --time-limits 1 10
```

Shared CLI options include:

```text
--config CONFIG
--solver SOLVER
--time-limits SECONDS...
--wall-time-tolerance FLOAT
--watchdog-multiplier FLOAT
--watchdog-grace-seconds FLOAT
--output PATH
--run-kind quick|candidate|tag
--nightly | --no-nightly
--release-tag TAG
--save-postgres | --no-save-postgres
--postgres-url URL
--log-level LEVEL
--log-dir PATH
--log-file PATH
--show-solver-output | --no-show-solver-output
--capture-solver-output | --no-capture-solver-output
```

`cvrp` adds `--num-instances`. `employee-scheduling` and
`job-shop-scheduling` add `--dataset-set` and `--datasets`.

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

## Logging

Every benchmark run writes a run log and, by default, per-solver stdout/stderr
logs. The default paths are:

```text
logs/<benchmark>_<run_stamp>/<benchmark>_<run_stamp>.log
logs/<benchmark>_<run_stamp>/solvers/<instance>__<solver>__<time_limit>s.stdout.log
logs/<benchmark>_<run_stamp>/solvers/<instance>__<solver>__<time_limit>s.stderr.log
```

When `--log-dir PATH` is provided, `PATH` is treated as a parent directory and
the framework creates `PATH/<benchmark>_<run_stamp>/...`. When `--log-file PATH`
is provided, the run log uses that exact file and solver captures are written
under `PATH`'s parent in a `<log_stem>_<benchmark>_<run_stamp>/solvers/`
directory.

Solver output is mirrored to the benchmark console and persisted to files. Use
`--no-show-solver-output` to keep the console quieter while still capturing
files, or `--no-capture-solver-output` to disable per-solver output files.
Solver exceptions are caught per solver/case/time-limit and become result rows
with `run_error`; full tracebacks are kept in the stderr/run logs. Fatal output
integrity errors, such as CSV or PostgreSQL write failures, still fail the run.

## TOML Configuration

The unified harness can read benchmark settings from a TOML file:

```sh
PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src \
  .venv/bin/python3 scripts/run_benchmark.py --config benchmark.example.toml
```

The config file may select the benchmark, solvers, time limits, run catalog
kind, nightly flag, output path, watchdog settings, benchmark-specific filters,
logging settings, and PostgreSQL persistence:

```toml
benchmark = "cvrp"
solver = ["pyvrp"]
time_limits = [1]
run_kind = "quick"
nightly = false

[postgres]
save = false
url = "postgresql://postgres@localhost/solverforge_bench"

[logging]
level = "INFO"
show_solver_output = true
capture_solver_output = true

[benchmarks.cvrp]
num_instances = 3

[benchmarks.employee-scheduling]
dataset_set = "quick"
datasets = ["n005w4"]

[benchmarks.job-shop-scheduling]
dataset_set = "quick"
datasets = ["ft06"]
```

Command-line options override TOML values. `release_tag` qualifies only the
effective `run_kind = "tag"` catalog. If a tag-oriented TOML file is run with a
CLI override such as `--run-kind quick` or `--run-kind candidate`, the TOML tag
does not carry into the overridden run; an explicit CLI `--release-tag` with a
non-tag run kind is rejected. Make targets accept the same file through
`BENCH_CONFIG`:

```sh
make bench-cvrp-quick BENCH_CONFIG=benchmark.example.toml
```

Append child harness options with `BENCH_ARGS`, or for the two-benchmark
nightly target with `NIGHTLY_ARGS`. `NIGHTLY_ARGS` may supply its own
`--config`; otherwise `make bench-nightly-db` uses `BENCH_CONFIG` when set and
falls back to `benchmark.nightly.example.toml`.

Set `nightly = true` for cron-driven runs that should be kept distinct from
normal runs with the same `run_kind`. Set `[postgres].save = true` or pass
`--save-postgres` to persist with the configured URL. A TOML PostgreSQL URL by
itself does not enable persistence; an explicit CLI `--postgres-url` does.
Use `benchmark.nightly.example.toml` as the cron-oriented template for the
combined nightly job; the nightly Make target runs the same root harness once
per benchmark with that config.

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

Set `DATABASE_URL` or `BENCH_DATABASE_URL` to point the Makefile database
targets at another benchmark warehouse.

Prepare the database and apply migrations:

```sh
make db-check
make db-create
make db-migrate
make db-reset
```

`db-reset` drops the configured database, recreates it, and runs migrations.
It passes `-y -f` by default so the helper works from non-interactive shells
and terminates existing PostgreSQL sessions on the benchmark database.
Override SQLx flags with `DB_RESET_FLAGS` when needed.

The database targets require `sqlx-cli` on `PATH`:

```sh
cargo install sqlx-cli --no-default-features --features postgres
```

Save a benchmark run to PostgreSQL while still writing the normal CSV:

```sh
PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src \
  .venv/bin/python3 scripts/run_benchmark.py cvrp \
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

`nightly` is stored separately from `run_kind`; a run may be nightly and still be
`quick`, `candidate`, or `tag`.

The normal benchmark Make targets are CSV-only. Use the `-db` variants to apply
migrations and save the same run to PostgreSQL as well:

```sh
make bench-cvrp-quick
make bench-cvrp-quick-db
make bench-employee-scheduling-quick
make bench-employee-scheduling-quick-db
make bench-job-shop-scheduling-quick
make bench-job-shop-scheduling-quick-db
make bench-cvrp-db BENCH_ARGS="--run-kind tag --release-tag v0.19.0"
make bench-cvrp-db BENCH_ARGS="--run-kind quick --nightly"
make bench-nightly-db
```

For the stock SolverForge architecture guardrail:

```sh
make verify-stock-solverforge-guardrails
```

Override the fixed JSPLIB subset or time limits with `GUARDRAIL_ARGS`, for
example:

```sh
make verify-stock-solverforge-guardrails GUARDRAIL_ARGS="--jssp-subset ft10 ta01 --time-limits 1 10"
make verify-stock-solverforge-guardrails GUARDRAIL_ARGS="--require-jssp-win"
```

`make bench-nightly-db` is the cron entrypoint. It builds all benchmark stacks,
applies migrations once, then calls `scripts/run_benchmark.py` directly for
CVRP, employee scheduling, and job-shop scheduling in parallel on their
per-suite pinned cores. By default it uses `benchmark.nightly.example.toml`;
set `BENCH_CONFIG` for a different nightly config, or append explicit child
harness overrides with `NIGHTLY_ARGS`. It does not pass `--solver`, so each
benchmark uses its full problem-specific default solver set, including both
native `solverforge` and `solverforge-py`.

## Result Schema

Benchmark runs now write one global snake_case CSV schema directly. Native
problem fields are stable optional columns, for example `nurses`, `weeks`,
`validator_model_delta`, `score_drift`, `num_jobs`, `num_machines`,
`num_operations`, `source_family`, `known_best_makespan`,
`lower_bound_makespan`, `upper_bound_makespan`, and `makespan_gap_to_best`.

PostgreSQL stores run-level catalog data in `benchmark_runs`, one solver-version
row per solver involved in the run in `benchmark_solver_versions`, and one row
per solver/case/time-limit result in `benchmark_results`. Each result references
the corresponding solver-version row with a foreign key. The live persistence
path uses a Polars DataFrame ETL boundary fed by in-memory `BenchmarkRow`
objects; generated CSV files are evidence artifacts, not the PostgreSQL source
of truth. Core benchmark columns are typed columns. Benchmark-specific native
fields are preserved in `native_fields`, and the complete emitted row is
preserved in `row_payload`. Native solver versions are recorded from the built
executables, not from Makefile default variables.
Runs have an independent `nightly` flag and are catalogued as `running`,
`completed`, or `failed`; each completed result row is persisted immediately, so
interrupted runs keep their partial rows but are excluded from latest-run display
views.
Run logs are linked from `benchmark_runs.log_path`; solver output logs are
linked from `benchmark_results.solver_stdout_path` and
`benchmark_results.solver_stderr_path`.
PostgreSQL is the warehouse source of truth. Display consumers should read
`benchmark_result_facts`, `latest_benchmark_runs`, or
`latest_benchmark_result_facts` instead of reconstructing the run/result join
themselves. The latest-run views keep normal and nightly runs separate.

For file-based loading, `scripts/normalize_results.py` normalizes generated
global CSV artifacts through Polars:

```sh
make normalize-results INPUT=path/to/benchmark.csv OUTPUT=results/normalized.csv
make normalize-results INPUT=path/to/benchmark.csv OUTPUT=results/normalized.ndjson ARGS="--format ndjson"
```

If a filtered run produces no result rows, the CSV remains a valid schema-only
artifact and normalizes to a schema-only output file.

The normalized rows use these columns:

```text
run_id, benchmark_name, benchmark_category, dataset, dataset_set, instance,
instance_size, solver, solver_version, time_limit_seconds, actual_time_seconds,
overshoot_seconds, overshoot_ratio, wall_time_over_limit,
watchdog_limit_seconds, watchdog_killed, run_error, solver_stdout_path,
solver_stderr_path, hard_feasible, cost, reported_cost, fresh_cost,
reference_cost, quality_ratio, validation_error, solution_artifact, nurses,
weeks, validator_model_delta, score_drift, num_jobs, num_machines,
num_operations, source_family, known_best_makespan, lower_bound_makespan,
upper_bound_makespan, makespan_gap_to_best, source_file
```
