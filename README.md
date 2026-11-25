# solverforge-bench

This repository is the official benchmark surface for SolverForge comparison work.
It groups benchmarks by SolverForge solve shape and runs every problem through
one shared framework: the framework owns the CLI, TOML configuration, benchmark
registry, exact run-matrix attestation, timing, overshoot calculation, watchdog
containment, result rows, CSV writing, production logging, solver stdout/stderr
capture, runtime provenance, and optional PostgreSQL persistence. Problem
packages are adapters: they load/select cases, create solver callables,
validate/evaluate returned solutions, and expose native fields.
See `WIREFRAME.md` for the current as-built repository map.

## Benchmarks

- `list-variable/cvrp/` is the canonical CVRP comparison imported from
  `~/hack/cvrp_solver_comparison`. It compares commercially usable Python solver
  integrations, Timefold, and the SolverForge CVRP
  list-variable runtime. `solverforge` is the native Rust/PyO3 adapter and
  `solverforge-py` is the public Python-binding model path. `highs` runs the
  HiGHS C++ core through the pinned `highspy==1.16.0` wheel on a two-index
  MILP with single-commodity load flows over the rounded edge-weight matrix.
- `scalar-variable/employee-scheduling/` is the nurse rostering benchmark. It
  uses the bundled INRC-II TXT corpus and compares `solverforge`,
  `solverforge-py`, `timefold`, `ortools`, and `highs` on nurse-to-shift
  assignments. The Python-binding path is a first-class default row for public
  scalar assignment-group coverage. `highs` mirrors the OR-Tools CP-SAT model
  (coverage, run-length bounds, weekends, requests) as a MILP with identical
  weights.
- `scalar-variable/job-shop-scheduling/` is the job-shop scheduling benchmark. It
  uses the bundled classic JSPLIB corpus for machine scheduling with job
  precedence and disjunctive machine capacity constraints. It compares
  `solverforge`, `solverforge-py`, `timefold`, `ortools`, and `highs` on
  fixed-machine operation start times. The Python-binding path exercises list
  variables, owner hooks, precedence hooks, and the public first-class list
  precedence/makespan constraint as a default comparison row.
  The SolverForge adapter is a Rust/PyO3 planning model, the Timefold adapter
  is a Java fat JAR, and the OR-Tools adapter is a native C++ CP-SAT
  executable. `highs` encodes the same disjunctive MILP the CP-SAT adapter
  covers, from zero starts. The SolverForge adapter maps JSPLIB data into stock list
  variables and the upstream `ListPrecedenceMakespanConstraint`; it does not
  provide benchmark-local search helpers or warm-start schedules.
- `huge-scale/hospital-scale/` is the huge-scale category (`huge_scale`): a
  synthetic hospital rostering problem with the solverforge-hospital ruleset at
  up to 100,000 shifts and 10,000 employees. It compares native `solverforge`,
  `timefold`, and `ortools` (CP-SAT). Instances are generated, not official, so
  rows carry no reference value and compare on validator cost.
- `huge-scale/delivery-scale/` is the second huge-scale benchmark: synthetic
  delivery routing with time windows under the solverforge-deliveries ruleset,
  at 10,000 stops on a fixed fleet. It compares native `solverforge` (the stock
  SolverForge routing model), `timefold`, `ortools` (the routing library), and
  `pyvrp`. 20,000 stops is the ceiling for
  SolverForge's routing model on this host: it holds two full stop-to-stop
  matrices, 6.4 GB at 20,000 stops and 40 GB at 50,000.

## Documentation Map

- `README.md` is the operator guide for setup, benchmark commands, configuration,
  persistence, and result schema.
- `AGENTS.md` is the maintainer and agent contract for scoped changes.
- `WIREFRAME.md` is the current as-built structure and data-flow map.
- `archive/README.md` marks archived reports and standalone scripts as
  historical material only.

## Dashboard

- `dash/` is a read-only Rails 8 dashboard over the benchmark PostgreSQL
  warehouse. It renders KPIs, standings, timelines, and recent runs from the
  warehouse's own reporting views (`latest_benchmark_runs`,
  `benchmark_result_facts`, `latest_benchmark_result_facts`) and never writes
  benchmark rows or runs warehouse migrations.
- Rails keeps its own framework metadata (cache, queue, cable) in local SQLite
  files under `dash/storage/`. Those files, `dash/log/`, `dash/tmp/`, and
  `dash/config/master.key` are runtime state and are never committed.
- The warehouse connection defaults to
  `postgresql://postgres@localhost/solverforge_bench`; set `BENCH_DATABASE_URL`
  (root Makefile) or pass `DATABASE_URL` overrides through the dash targets.

```sh
make dash-setup            # bundle install + prepare the Rails metadata DB
make dash-server           # serve the dashboard (default http://127.0.0.1:3001)
make dash-warehouse-check  # verify the warehouse connection
make dash-smoke            # load a dashboard snapshot from the warehouse
make dash-test             # run the Rails test suite
```

`make dash-*` targets delegate to `dash/Makefile`, which keeps the full Rails
workflow (`lint`, `security`, `console`, `routes`, deployment via Kamal).

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
the exact published `solverforge==0.8.1` wheel into the same `.venv`, so
`solverforge-py` benchmark rows never depend on global Python packages or a
sibling checkout.

The CVRP, employee-scheduling, job-shop, hospital-scale, and delivery-scale
native SolverForge adapters are pinned to the exact published SolverForge `0.31.2` crates with committed
registry lockfiles. A git-locked SolverForge dependency, when an adapter
temporarily tracks unreleased work, reports its version as
`<crate version>+git.<commit>`. The `solverforge-py` adapters require the exact
published `solverforge==0.8.1` distribution and report that installed
distribution version in CSV and PostgreSQL rows.

Each workload keeps two separate SolverForge configuration artifacts: the
native adapter's `solver.toml` and the Python adapter's `solverforge_py.toml`.
The files must parse to the same policy. CVRP uses the full qualified
construction and seven-neighborhood local-search policy. Employee scheduling
and JSSP intentionally leave phases unspecified so both bindings select the
same model-aware SolverForge defaults. At runtime, both adapters change only
the requested termination seconds. `make verify-solverforge-config-parity`
rejects semantic drift and also rejects replacing both files with an equally
weaker policy. Hospital-scale has no Python adapter, so its single native
`solver.toml` sets only the seed and leaves phases to the SolverForge defaults.
Delivery-scale has no Python adapter either; its `solver.toml` is the
solverforge-deliveries policy with Clarke-Wright construction completed by
cheapest insertion and the ruin move selector removed (see Delivery-Scale
Commands).

Benchmark run targets execute the shared harness through `taskset` with
different default pinned cores: `CVRP_BENCH_CPU ?= 0`,
`EMPLOYEE_BENCH_CPU ?= 1`, `JOBSHOP_BENCH_CPU ?= 2`,
`HOSPITAL_SCALE_BENCH_CPU ?= 3`, and `DELIVERY_SCALE_BENCH_CPU ?= 4`. They set
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
valid fair-start witnesses. A reference solver that ends its time limit without
a schedule (`no_solution` or `no_incumbent`) is recorded as its result; any
other reference error, an invalid fair start, or a watchdog kill fails the
guardrail. Add `--require-jssp-win` through `GUARDRAIL_ARGS`
when checking the final JSSP win condition.

## SolverForge-Py Adapter Test Gate

`solverforge-py` is part of the default quick, canonical, and nightly solver
sets for every benchmark class. Before release work, public benchmark claims,
or changes to the Python-binding solver paths, refresh the root `.venv` with
`make install-python-deps`; after publication, that target force-refreshes the
exact `solverforge==0.8.1` wheel in the benchmark environment.

Run the local/release guardrails explicitly:

```sh
make verify-solverforge-config-parity
make verify-benchmark-contracts
make verify-solverforge-py-guardrail-contract
make verify-solverforge-py-smoke
make verify-solverforge-py-comparison
make verify-solverforge-py-release
```

The configuration gate is a prerequisite of every native SolverForge build and
every native/Python guardrail. The guardrail-contract gate exercises exact
matrix coverage and secret-redaction regressions without running a solver. The
shared benchmark-contract gate separately exercises the root runner's
nonempty/unique/exact matrix contract, runtime artifact provenance, and
SolverForge output-completeness boundaries across every benchmark. The
smoke gate remains a focused
`solverforge-py` adapter check for CVRP,
employee scheduling, and the JSSP quick group. Employee rows check fair-start,
runtime, version, and score-reporting integrity while accepting an honest
infeasible or no-incumbent outcome. A one-second production-scale employee
probe covers `n030w4`, `n050w8`, and `n080w8` and requires every row to return
a hard-feasible schedule without a validation error. The comparison gate runs paired
native `solverforge` and `solverforge-py` rows, resolves every requested dataset
selector before execution, requires every expected instance/time-limit/solver
row exactly once, validates fair-start and execution integrity without turning
employee feasibility into a gate, and writes a
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
run `make validate-cvrp`, run `make validate-employee-model-parity`, and run
the corpus and model-parity validators of both huge-scale suites. The parity script requires that root
`.venv`, so CI must use the Makefile bootstrap instead of a detached
`python -m pip install -e .`.

The Rust jobs keep `--locked` resolution strict. The CVRP, employee,
job-shop, hospital-scale, and delivery-scale SolverForge manifests and
lockfiles target SolverForge `0.31.2`. The jobs set the PyO3 Python
environment from `actions/setup-python`, then run formatting,
`cargo clippy --locked --all-targets -- -D warnings`, and `cargo build --locked`
for the CVRP SolverForge adapter, CVRP rustvrp adapter, employee scheduling
SolverForge adapter, job-shop scheduling SolverForge adapter, and both
huge-scale SolverForge adapters. GitHub uses
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

`bench-cvrp-quick` uses the default CVRP solver set on three instances at
`1` and `10` seconds, including both native `solverforge` and
`solverforge-py`. The optional `vroom` and `rustvrp` adapters stay registered
but are no longer default rows; pass `--solver vroom --solver rustvrp` to run
them ad hoc. The `bench-cvrp-solverforge-*` targets keep the
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
The Python-binding adapter keeps skill and initial-history exclusions in each
shift's native candidate domain and supplies adjacent forbidden successions as
native same-value conflict rows, so construction and grouped local search use
the same hard assignment boundary.

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

## Hospital-Scale Commands

Check that the committed corpus reproduces from its generator and that every
instance has a hard-feasible hidden witness, then check that every solver model
encodes the validator's ruleset:

```sh
make validate-hospital-scale
make validate-hospital-scale-model-parity
```

Build the SolverForge, Timefold, and OR-Tools integrations and run the quick or
canonical benchmark:

```sh
make build-hospital-scale
make bench-hospital-scale-quick
make bench-hospital-scale
```

The corpus lives in `huge-scale/hospital-scale/data/hospital/`. `manifest.json`
pins the SHA-256 of every gzip instance and witness:

| Instance | Employees | Shifts | Group |
| --- | --- | --- | --- |
| `hs-e1000-s10000` | 1,000 | 10,000 | `quick` (smoke test only) |
| `hs-e10000-s100000` | 10,000 | 100,000 | `canonical` |

Each instance covers a 28-day horizon over seven care hubs, 17 skills, and
five shift templates (early, day, late, 12-hour long day, overnight).
`scripts/generate_instances.py` draws a feasible hidden roster first and
derives shifts, unavailability, and day preferences from it. `--check`
regenerates everything in memory and fails on any byte of drift. The witness is
read only by `scripts/validate_all.py`; no solver receives it.

The ruleset is solverforge-hospital's. Hard rules: every shift assigned, the
required skill held, no overlapping shifts, at least 10 hours of rest between
shifts, at most one shift per calendar day touched, and no shift touching an
unavailable day. Soft cost: +10 per undesired day touched, -10 per desired day
touched, and the sum over employees of the squared shift count. The squared
count replaces solverforge-hospital's standard-deviation balance so that every
solver and the validator compute the same integer. Every model receives the same
per-skill candidate domain from the shared input document.

OR-Tools solves the same rules as a CP-SAT model. Shifts with the same start,
end, and skill are interchangeable under every rule, so the model decides which
employees staff each such slot type (about 2,000 types, 1.6 million booleans
at canonical size instead of 90 million per-shift pairs) and the adapter hands
them to that type's shifts in instance order. Hard rules are constraints, an
unavailable employee never enters a slot's domain, and the squared count is a
product constraint. It runs one search worker with seed 1, like the other
CP-SAT adapters.

Every hospital-scale run, quick, canonical, and nightly, uses one 300-second
budget. `[benchmarks.hospital-scale]` accepts its own `time_limits`, which
override the root `time_limits` for this suite only. A run that ends with any
unassigned shift is a `no_solution` row, never a partial roster sent to the
validator.

## Delivery-Scale Commands

```sh
make validate-delivery-scale
make validate-delivery-scale-model-parity
make build-delivery-scale
make bench-delivery-scale-quick
make bench-delivery-scale
```

The corpus lives in `huge-scale/delivery-scale/data/deliveries/`, hash-pinned
by `manifest.json` like hospital-scale:

| Instance | Stops | Vehicles | Group |
| --- | --- | --- | --- |
| `ds-s2000` | 2,000 | 49 | `quick` |
| `ds-s10000` | 10,000 | 239 | `canonical` |

Stops lie on a 30 km by 30 km plane around one central depot, mostly in 60
neighbourhood clusters. Travel time is the Euclidean distance at 10 m/s,
rounded half up to whole seconds; the validator and every model compute it the
same way. `generator.py` builds a hidden fleet plan first: it sweeps around the
depot, cuts routes by capacity 200, 45 stops, and a 22:00 day end, and orders
each route by nearest neighbour. It then places every time window around that
plan's service time. The fleet is the witness route count plus 5% spare.

The ruleset is solverforge-deliveries'. Hard rules: every delivery assigned
exactly once, no more routes than vehicles, vehicle capacity, and every service
ending by its window's end (an early vehicle waits). The soft cost is total
travel seconds, depot to depot.

SolverForge uses its stock routing model (`solverforge::cvrp` matrices and
hooks) with one deliberate wiring choice and one policy change:

- Clarke-Wright merges go through `route_feasible` (capacity and time windows).
  The stock `domain = "cvrp"` savings hooks check route structure only, so
  their merges ignore both; the CVRP benchmark adapter wires the same strict
  hooks.
- Construction is `list_clarke_wright`, then `list_cheapest_insertion` for the
  stops the strict merges cannot place on the fixed fleet (about 6,400 of
  10,000), then `list_k_opt` with k = 2. On `ds-s10000` at 300 seconds this
  start ends at 765,965 against 1,477,795 for cheapest insertion from an
  empty plan and 852,168 for the SolverForge defaults, measured side by side.
- Local search is the solverforge-deliveries policy without the ruin move
  selector. Every local search with ruin moves at 10,000 stops made a few
  hundred steps in 150 seconds and ended with time windows or capacity
  violated.
- `solver.toml` records the full comparison, including the bounded
  `savings_neighbors` and CVRP-forager variants that ended worse.

Timefold computes travel from coordinates on demand and runs its default
phases.

OR-Tools uses its routing library with the same travel callback, a capacity
dimension, and a time dimension whose cumul is the service start (window
`[min_start, max_end - service]`, waiting as slack, departure fixed). Every stop
sits in a disjunction with the shared 1,000,000 unassigned-delivery penalty, so
a stop the search cannot place leaves the run a `no_solution` row instead of
failing it outright. Construction is parallel cheapest insertion and local
search is guided local search: path-cheapest-arc construction left 72 of the
10,000 canonical stops unplaced after 300 seconds.

PyVRP builds the full travel-seconds matrix (about 800 MB at 10,000 stops) and
uses it for both distance and duration, so its distance objective is total
travel time. A stop's latest service start is `max_end - service`, and every
vehicle leaves the depot at the departure time.

Every run uses one 300-second budget.

## Thread Study

`make thread-study` answers when SolverForge's parallel local search pays off:
it runs native SolverForge against itself at 1, 2, and 4 move threads on CVRP
and employee scheduling, at 10s and 60s budgets
(`benchmark.thread-study.toml`), then renders `build/thread-study/report.md`.

- The thread counts are solver variants: `solverforge-t2`, `solverforge-t4`,
  and `solverforge-t8` run the native adapter with that many local-search
  evaluators, the main director included. They are registered in each suite
  but never in a default matrix, so they never enter cross-solver rankings.
- Every run, the single-threaded baseline included, is pinned to the same CPU
  set, `THREAD_STUDY_CPUS ?= 4,6,8,10`: one logical CPU per physical core on a
  six-core SMT machine. Set it to your own cores to reproduce on other
  hardware; a thread count above the set's size only adds contention.
- Results stay in local CSVs; `[postgres] save = false` keeps them out of the
  warehouse.

Each report row compares a thread count to 1 thread on the same instance and
budget. Parallel evaluation runs only in local search, so every search figure
comes from the adapters' per-phase telemetry for the `Local Search` phase, not
from run totals: the cost change, the share of the run spent in local search,
the single-threaded run's share of local-search time spent evaluating moves
(together, the most parallel evaluation can speed up; construction and move
generation stay sequential), the useful-throughput ratio (local-search
evaluations consumed per second), the speculative share (evaluations parallel
windows discarded), evaluations per step, and a verdict from cost, with
differences inside 0.5% reported as ties. Rows from runs without phase records
leave the search figures blank. `make thread-study-report` re-renders the report
from existing CSVs.

## Unified Harness

The root entrypoint runs the shared framework with problem-specific specs:

```sh
PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src \
  .venv/bin/python3 scripts/run_benchmark.py cvrp --run-kind quick --num-instances 3 --time-limits 1 10

PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src \
  .venv/bin/python3 scripts/run_benchmark.py employee-scheduling --run-kind quick --datasets n005w4 --time-limits 1 10

PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src \
  .venv/bin/python3 scripts/run_benchmark.py job-shop-scheduling --run-kind quick --dataset-set quick --time-limits 1 10

PYTHONPATH=src:huge-scale/hospital-scale/src \
  .venv/bin/python3 scripts/run_benchmark.py hospital-scale --run-kind quick --dataset-set quick --time-limits 300

PYTHONPATH=src:huge-scale/delivery-scale/src \
  .venv/bin/python3 scripts/run_benchmark.py delivery-scale --run-kind quick --dataset-set quick --time-limits 300
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

`cvrp` adds `--num-instances`. `employee-scheduling`,
`job-shop-scheduling`, `hospital-scale`, and `delivery-scale` add
`--dataset-set` and `--datasets`.

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
When SolverForge reaches the requested time limit before mandatory construction
is complete, the row records `termination_status=no_solution`, no objective,
and the original native exception type and message. Other SolverForge
exceptions remain `adapter_error`.
The runner materializes the selected cases before execution, rejects empty or
duplicate selections and nonpositive or duplicate time limits, and requires
exactly one emitted row for every case/solver/time-limit key before a run can
complete.

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

# The huge-scale suites accept their own time_limits, overriding the root value.
[benchmarks.hospital-scale]
dataset_set = "quick"
time_limits = [300]

[benchmarks.delivery-scale]
dataset_set = "quick"
time_limits = [300]
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
make bench-hospital-scale-quick
make bench-hospital-scale-quick-db
make bench-delivery-scale-quick
make bench-delivery-scale-quick-db
make bench-cvrp-db BENCH_ARGS="--run-kind tag --release-tag v0.19.10"
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
CVRP, employee scheduling, job-shop scheduling, hospital-scale, and
delivery-scale in parallel on their per-suite pinned cores. The two huge-scale
suites run their single 300-second budget from their own `[benchmarks.*]`
tables; hospital-scale runs three solvers and delivery-scale four, at about 5
minutes per solver. By default it uses `benchmark.nightly.example.toml`;
set `BENCH_CONFIG` for a different nightly config, or append explicit child
harness overrides with `NIGHTLY_ARGS`. It does not pass `--solver`, so each
benchmark uses its full problem-specific default solver set, including both
native `solverforge` and `solverforge-py`.

## Result Schema

Benchmark runs now write one global snake_case CSV schema directly. Native
problem fields are stable optional columns, for example `nurses`, `weeks`,
`validator_model_delta`, `score_drift`, `num_jobs`, `num_machines`,
`num_operations`, `source_family`, `known_best_makespan`,
`lower_bound_makespan`, `upper_bound_makespan`, `makespan_gap_to_best`,
`makespan_gap_to_reference`, and `reference_kind`.

PostgreSQL stores run-level catalog data in `benchmark_runs`, one solver-version
row per solver involved in the run in `benchmark_solver_versions`, and one row
per solver/case/time-limit result in `benchmark_results`.
`benchmark_run_matrix_entries` stores every expected result key before the
first solver starts. Each result references both the corresponding
solver-version row and an expected matrix key with foreign keys. The live
persistence path uses a Polars DataFrame ETL boundary fed by in-memory `BenchmarkRow`
objects; generated CSV files are evidence artifacts, not the PostgreSQL source
of truth. Core benchmark columns are typed columns. Benchmark-specific native
fields are preserved in `native_fields`, and the complete emitted row is
preserved in `row_payload`. Solver provenance hashes the actual installed
Python distribution, executable, native adapter binary, or shaded JAR. Cargo
adapters additionally record the registry-backed locked dependency version and
checksum; SolverForge adapters record the qualified semantic policy hash.
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
themselves for warehouse diagnostics. Public consumers must use
`publishable_benchmark_runs`, `publishable_benchmark_result_facts`, or their
`latest_publishable_*` counterparts. Those views admit only completed runs from
a clean, identified commit with an exact expected/observed matrix, valid
fair-start witnesses, complete runtime provenance, and pinned inputs. Solver failure rows are
allowed in an otherwise complete matrix; they reduce feasibility and never
contribute a fabricated quality value. The latest-run views keep normal and
nightly runs separate.

A run is attributed to its commit only when the checkout holds no unreconciled
change to the harness: tracked file modifications (staged or not), and untracked
files under `src/`, `scripts/`, `list-variable/`, or `scalar-variable/`, all make
`git_dirty` true and withhold publication. Untracked output outside those roots —
`build/`, `logs/`, per-solver `target/`, the dashboard's `storage/`, export
directories, and stray scratch files the benchmark never reads — is runtime
state, not a claim about the harness, and does not fail the gate. Those paths are
recorded per run in `benchmark_runs.metadata.worktree`, and
`src/solverforge_bench/postgres.py` is the single place that decides what counts,
so the rule and the recorded flag cannot drift apart.

For file-based loading, `scripts/normalize_results.py` normalizes generated
global CSV artifacts through Polars:

```sh
make normalize-results INPUT=path/to/benchmark.csv OUTPUT=results/normalized.csv
make normalize-results INPUT=path/to/benchmark.csv OUTPUT=results/normalized.ndjson ARGS="--format ndjson"
```

If a requested selector resolves to no cases, the harness fails before opening
CSV or PostgreSQL output; an empty matrix is never a completed benchmark.

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
upper_bound_makespan, makespan_gap_to_best, makespan_gap_to_reference,
reference_kind, source_file
```

Job-shop reference metrics use the pinned official ScheduleOpt JSPLIB
best-known-solutions catalog in
`scalar-variable/job-shop-scheduling/data/jsplib/best_known_solutions.json`.
Closed instances are labelled `known_optimum`; open instances use the official
best-known upper bound and are labelled `best_known_upper_bound`. The latter is
a reference solution value, not a proof of optimality.

## Official references

Every problem resolves its reference from a versioned catalog beside its
instances, `references.json`, through `solverforge_bench.references`. One
mechanism decides what a gap is measured against, and each value carries the
source that published it, that source's revision, and whether it is a proven
optimum or a best known upper bound -- comparing across those kinds compares
different claims, so the kind travels with the value.

| Problem | Catalog | Source |
| --- | --- | --- |
| `cvrp` | `list-variable/cvrp/data/X/references.json` | CVRPLIB Set X table (Uchoa et al. 2017); its `Opt` column gives 61 optima and 39 best known bounds |
| `job-shop-scheduling` | `scalar-variable/job-shop-scheduling/data/jsplib/references.json` | ScheduleOpt best-known catalogue; 147 closed, 15 open |
| `employee-scheduling` | `scalar-variable/employee-scheduling/data/inrc2/references.json` | INRC-II official test dataset; the nine tuples the competition published reference solutions for, scored by the official validator |

Regenerate a catalog from its source, and check that a committed catalog still
matches the source it claims:

```sh
make verify-reference-catalogs     # every catalog reproduces from its source
make refresh-reference-sources     # re-read the official sources from upstream
make load-reference-catalogs       # carry the committed values into PostgreSQL
```

`verify-reference-catalogs` fails when a committed value no longer regenerates,
so a hand-edited reference cannot reach the warehouse.

`refresh-reference-sources` (`scripts/refresh_reference_sources.py`) re-reads the
ScheduleOpt catalogue at the head of its default branch and the CVRPLIB Set X
table, rewrites the committed source files only when a value the benchmark uses
moved, and regenerates the affected catalogs. INRC-II values are frozen since
the competition closed, so employee scheduling has nothing to refresh. Pass
`REFRESH_ARGS=--check` to report without writing. The Forgejo workflow
`.forgejo/workflows/refresh-references.yml` runs it every Monday and opens or
updates a pull request on `refresh/reference-sources` when upstream moved; a new
value reaches runs only once that pull request is merged.

Every run opened with `--save-postgres` syncs the warehouse to the committed
catalogs before it starts, through the warehouse function
`benchmark_sync_reference_catalog`: `benchmark_reference_catalog` becomes
exactly the committed values, and the catalog is recorded as an immutable
version in `benchmark_reference_catalog_versions`, whose SHA-256 the run stores
in `benchmark_runs.reference_catalog_sha256`. `load-reference-catalogs` performs
the same sync on demand. `benchmark_reference_resolved` reports the effective
reference per result, preferring the current official value and falling back to
whatever the run recorded when the catalog has no entry.

The run also pins its instances. The harness hashes each loaded instance once
(the same SHA-256 the fair-start witness carries as `solver_input_hash`) and
`benchmark_record_run_instances` stores it in `benchmark_run_instances`, with
every distinct version in `benchmark_instances`. A trigger refuses a result row
for an instance the run did not pin, and `benchmark_instance_versions` flags an
instance name that has been run with more than one hash. Publication requires a
known catalog version, one pinned hash per matrix instance, every recorded
`reference_cost` equal to the pinned catalog value, and every witness input hash
equal to the pinned instance hash. Runs recorded before pinning existed carry
`input_pinning_required = false` and are audited as before.

The bundled CVRP `.sol` files hold one feasible tour per instance and are not
official values, so they are not used as references. Employee scheduling runs
instances outside the published test set without a reference, and reports that
absence rather than substituting a bound of its own. Hospital-scale and delivery-scale
instances are synthetic and have no catalog: their rows leave `reference_cost` and
`quality_ratio` empty and compare on validator cost.
