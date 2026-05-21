# SolverForge Bench Wireframe

This is the as-built map for the current benchmark repository. It is a
documentation contract: when source layout, benchmark ownership, run flow,
persistence, or CI changes, update this file with `README.md` and `AGENTS.md`.

## Repository Surfaces

- `pyproject.toml` declares the Python 3.14 package, shared dependencies, and
  package discovery across `src/`, `list-variable/cvrp/src/`, and
  `scalar-variable/employee-scheduling/src/`.
- `Makefile` is the root build and execution surface. It owns virtualenv setup,
  native adapter builds, benchmark smoke/full runs, database helpers,
  normalization, the SolverForge banner, and CPU-pinned harness execution.
- `src/solverforge_bench/` is the shared framework. It owns CLI parsing, TOML
  loading, benchmark registry, run matrix construction, timed execution,
  watchdog containment, row construction, CSV writing, logging, solver output
  capture, solver-version collection, ETL, and optional PostgreSQL writes.
- `scripts/run_benchmark.py` and benchmark-local validation scripts bootstrap
  through `scripts/_venv_bootstrap.py` when they require the repository
  virtualenv.
- `list-variable/cvrp/` is the list-variable benchmark package for CVRP.
- `scalar-variable/employee-scheduling/` is the scalar-variable benchmark
  package for INRC-II nurse scheduling.
- `migrations/` holds SQLx-compatible PostgreSQL warehouse migrations.
- `.github/workflows/ci.yml` holds the split GitHub/Forgejo CI workflow.
- `archive/` holds historical reports and older standalone scripts only.

## Shared Harness Flow

1. `scripts/run_benchmark.py` bootstraps into the root `.venv`, adds the three
   source roots to `sys.path`, and delegates to `solverforge_bench.cli.main`.
   `scripts/verify_model_parity.py` uses the same virtualenv bootstrap before
   importing the employee-scheduling package.
2. `cli.py` loads optional TOML configuration, selects the benchmark spec,
   applies CLI overrides, finalizes run catalog fields, validates solver names,
   and passes the selected spec to `runner.py`.
3. `registry.py` exposes the canonical benchmark specs: `cvrp` and
   `employee-scheduling`.
4. `runner.py` resolves cases, time limits, solvers, solver versions, output
   paths, artifact paths, run logs, and solver output paths. It then iterates
   `case -> time_limit -> solver`.
5. `execution.py` runs each solver in a child process. The nominal time limit is
   passed to the solver; it is not the hard kill deadline. The watchdog only
   terminates runaway processes after `max(time_limit * multiplier,
   time_limit + grace_seconds)`.
6. Each benchmark spec validates and evaluates returned solutions, then the
   shared runner writes an incremental CSV row and, when enabled, a PostgreSQL
   row.
7. Solver exceptions, including `NoSolutionFoundError`, become result rows with
   `run_error`. CSV or PostgreSQL write failures remain fatal output-integrity
   failures.

## Benchmark Specs

| Spec | Category | Default solvers | Default time limits | Native columns |
| --- | --- | --- | --- | --- |
| `cvrp` | `list_variable` | `pyvrp`, `ortools`, `vroom`, `timefold`, `rustvrp`, `pyhygese`, `solverforge` | `1`, `10`, `60` | none |
| `employee-scheduling` | `scalar_variable` | `solverforge`, `timefold`, `ortools` | `1`, `10`, `60` | `nurses`, `weeks`, `validator_model_delta`, `score_drift` |

## CVRP Adapter Shape

- Data lives under `list-variable/cvrp/data/X/` as CVRPLIB-X `.vrp` and `.sol`
  pairs.
- `spec.py` exposes dataset `CVRPLIB-X`, dataset set `canonical`, and
  `--num-instances` for smoke selection.
- `domain/models.py` defines Pydantic instance and solution contracts.
- `domain/utils.py` validates route feasibility and cost.
- `solver/solver.py` registers `pyvrp`, `ortools`, `vroom`, `timefold`,
  `rustvrp`, `pyhygese`, and `solverforge`.
- Native solver builds are rooted in `solver/ortools/`, `solver/rustvrp/`,
  `solver/vroom/`, `solver/timefold/`, and `solver/solverforge/`.
- The SolverForge CVRP adapter is pinned to SolverForge `0.14.1` and resolves
  the sibling checkout at `../solverforge/crates/solverforge` from the
  repository root.
- The CVRP model uses public SolverForge CVRP list-variable hooks:
  `VrpSolution`, matrix distance meters, route get/set/depot hooks, route
  metric classes, route distance, and route feasibility. The benchmark budget
  is applied through the model config provider.
- `solverforge/solver.toml` uses reproducible mode, seed `42`, a 60 second
  internal termination cap, list construction phases, and a local-search union
  of nearby list moves, reverse moves, k-opt, ruin, and limited-neighborhood
  sublist change moves.
- Native OR-Tools no-solution exits are normalized to `NoSolutionFoundError`
  rather than benchmark-aborting runtime errors.

## Employee Scheduling Adapter Shape

- Data lives under `scalar-variable/employee-scheduling/data/inrc2/` as bundled
  INRC-II scenario, history, week-data, and reference solution TXT files.
- `manifest.json` defines dataset groups: `quick` has 1 group and 3 cases,
  `test_with_solutions` has 3 groups and 9 cases, `canonical` has 14 groups and
  42 cases, and `late` has 6 groups and 18 cases.
- `loader.py` parses INRC-II TXT files and enumerates concrete cases.
- `validation.py` is the shared Python referee. It checks hard constraints first
  and then computes the soft-cost breakdown.
- `scripts/verify_model_parity.py` verifies that the Python validator,
  OR-Tools model, Timefold model, and SolverForge model encode the same model
  contract.
- `spec.py` exposes `--dataset-set` and `--datasets`, writes solution JSON
  artifacts for hard-feasible runs, and reports validator/model deltas through
  native columns.
- `solver/solver.py` registers `solverforge`, `timefold`, and `ortools`.
- The SolverForge NRP adapter is pinned to SolverForge `0.15.0` with `serde`
  enabled and resolves the node-sharing compiler sibling checkout at
  `../solverforge-node-sharing/crates/solverforge` from the repository root.
- The SolverForge NRP model uses public scalar APIs: per-shift candidate
  values, unassigned scalar variables for optional slots, nearby value/entity
  candidates, and one `ScalarGroup::assignment` for required minimum slots,
  one nurse per day capacity, adjacent forbidden-succession assignment rules,
  ordered shift positions, and nurse sequence keys.
- `solverforge_nrp/solver.toml` sets `environment_mode = "non_reproducible"`
  and `random_seed = 1`. It intentionally does not impose an independent
  termination cap; the shared harness passes the requested benchmark budget.

## Makefile Contract

- `make install-python-deps` creates or refreshes the root `.venv`.
- `make build-cvrp` builds Python dependencies plus CVRP Timefold, SolverForge,
  OR-Tools, rustvrp, and VROOM integrations.
- `make build-employee-scheduling` builds Python dependencies plus employee
  Timefold, SolverForge, and OR-Tools integrations.
- `make bench-cvrp-quick` runs three CVRP instances at 1 and 10 seconds with
  all registered CVRP solvers.
- `make bench-cvrp-quick-db` runs the same CVRP smoke path after applying
  migrations and persists it to PostgreSQL.
- `make bench-cvrp-solverforge-quick` runs the same quick CVRP slice with only
  SolverForge.
- `make bench-cvrp-solverforge-quick-db` persists that same SolverForge-only
  CVRP smoke path after applying migrations.
- `make bench-employee-scheduling-quick` runs `n005w4` at 1 and 10 seconds with
  all registered employee-scheduling solvers.
- `make bench-employee-scheduling-quick-db` runs the same employee smoke path
  after applying migrations and persists it to PostgreSQL.
- `make bench-employee-scheduling-solverforge-quick` runs the same quick
  employee slice with only SolverForge.
- `make bench-employee-scheduling-solverforge-quick-db` persists that same
  SolverForge-only employee smoke path after applying migrations.
- `make bench-cvrp` and `make bench-employee-scheduling` run canonical
  benchmark paths at 1, 10, and 60 seconds.
- `make bench-nightly-db` builds both benchmark stacks, applies migrations once,
  and invokes the root harness once for CVRP and once for employee scheduling.
- `make db-check`, `make db-create`, `make db-migrate`, and `make db-reset`
  operate on `DATABASE_URL`, then `BENCH_DATABASE_URL`, then
  `postgresql://postgres@localhost/solverforge_bench`.
- `make normalize-results` converts generated global CSV artifacts to normalized
  CSV or NDJSON through `scripts/normalize_results.py`.
- Benchmark run targets use `taskset -c $(BENCH_CPU)` with `BENCH_CPU ?= 0` and
  set `OMP_NUM_THREADS=1` and `MKL_NUM_THREADS=1`.
- Override child harness arguments with `BENCH_ARGS`, nightly child arguments
  with `NIGHTLY_ARGS`, config path with `BENCH_CONFIG`, and SQLx reset flags
  with `DB_RESET_FLAGS`.

## Configuration Contract

- Root TOML keys are `benchmark`, `solver`, `time_limits`,
  `wall_time_tolerance`, `watchdog_multiplier`, `watchdog_grace_seconds`,
  `output`, `run_kind`, `nightly`, and `release_tag`.
- `[postgres]` accepts `save` and `url`.
- `[logging]` accepts `level`, `dir`, `file`, `show_solver_output`, and
  `capture_solver_output`.
- `[benchmarks.cvrp]` accepts `num_instances`.
- `[benchmarks.employee-scheduling]` accepts `dataset_set` and `datasets`.
- `run_kind` is one of `quick`, `candidate`, or `tag`; `tag` requires
  `release_tag`.
- A CLI `--postgres-url` enables PostgreSQL persistence unless
  `--no-save-postgres` is also supplied. A TOML PostgreSQL URL alone does not.

## Output And Persistence

- CSV output uses one global snake_case schema with stable optional native
  columns.
- `BenchmarkRow.as_dict()` emits core fields and merges native fields.
- CVRP output defaults to `list-variable/cvrp/data/benchmark_cvrp_<stamp>.csv`.
- Employee scheduling output defaults to
  `scalar-variable/employee-scheduling/data/benchmark_employee_scheduling_<stamp>.csv`.
- Employee scheduling solution artifacts are written under
  `scalar-variable/employee-scheduling/data/artifacts/employee_scheduling_<stamp>/`.
- PostgreSQL stores run catalog rows in `benchmark_runs`, solver-version rows in
  `benchmark_solver_versions`, and result rows in `benchmark_results`.
- `benchmark_result_facts`, `latest_benchmark_runs`, and
  `latest_benchmark_result_facts` are the display-facing warehouse views.
- Completed result rows are written immediately. Interrupted runs keep partial
  rows but are excluded from latest-run views unless their run status is
  completed.

## CI Contract

- Python CI runs on `ubuntu-latest` for GitHub and `python` runner labels for
  Forgejo.
- Rust CI runs on `ubuntu-latest` for GitHub and `rust` runner labels for
  Forgejo.
- Python CI uses `actions/setup-python@v6` with Python 3.14, creates the root
  `.venv` through `make install-python-deps HOST_PYTHON=...`, compiles Python
  source, parses benchmark TOML examples, validates bundled CVRP instances, and
  validates employee model parity.
- Rust CI clones SolverForge tag `v0.14.1` into
  `$GITHUB_WORKSPACE/../solverforge` and clones `feat/node-sharing-compiler`
  into `$GITHUB_WORKSPACE/../solverforge-node-sharing`, the exact relative paths
  declared by the active adapter `Cargo.toml` files. It checks formatting, runs
  `cargo clippy --locked --all-targets -- -D warnings`, and runs
  `cargo build --locked` for the CVRP SolverForge adapter, CVRP rustvrp
  adapter, and employee SolverForge adapter.

## Generated Artifacts

- The ignored build and output surfaces are `.venv/`, `__pycache__/`, Python
  package/build outputs, Rust/Java `target/` outputs, `logs/*`, generated
  benchmark CSVs, and generated solution artifact directories.
- Generated CSVs are evidence artifacts. Commit them only when the run output is
  intentionally part of the change.
