# SolverForge Bench Wireframe

This is the as-built map for the current benchmark repository. It is a
documentation contract: when source layout, benchmark ownership, run flow,
persistence, or CI changes, update this file with `README.md` and `AGENTS.md`.

## Repository Surfaces

- `pyproject.toml` declares the Python 3.14 package, shared dependencies, and
  package discovery across `src/`, `list-variable/cvrp/src/`, and
  `scalar-variable/employee-scheduling/src/`, and
  `scalar-variable/job-shop-scheduling/src/`.
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
- `scalar-variable/job-shop-scheduling/` is the scalar-variable benchmark
  package for classic JSPLIB job-shop scheduling.
- `migrations/` holds SQLx-compatible PostgreSQL warehouse migrations.
- `.github/workflows/ci.yml` holds the GitHub-hosted CI workflow.
- `.forgejo/workflows/ci.yml` holds the local Forgejo CI workflow.
- `archive/` holds historical reports and older standalone scripts only.

## Shared Harness Flow

1. `scripts/run_benchmark.py` bootstraps into the root `.venv`, adds the four
   source roots to `sys.path`, and delegates to `solverforge_bench.cli.main`.
   `scripts/verify_model_parity.py` uses the same virtualenv bootstrap before
   importing the employee-scheduling package.
2. `cli.py` loads optional TOML configuration, selects the benchmark spec,
   applies CLI overrides, finalizes run catalog fields, validates solver names,
   and passes the selected spec to `runner.py`.
3. `registry.py` exposes the canonical benchmark specs: `cvrp`,
   `employee-scheduling`, and `job-shop-scheduling`.
4. `runner.py` resolves cases, time limits, solvers, solver versions, output
   paths, artifact paths, run logs, and solver output paths. It then iterates
   `case -> time_limit -> solver`.
5. `execution.py` runs each solver in a child process. Only the instance payload
   and nominal time limit are passed to the solver callable; the nominal time
   limit is not the hard kill deadline. The watchdog only terminates runaway
   processes after `max(time_limit * multiplier, time_limit + grace_seconds)`.
6. Each benchmark spec validates and evaluates returned solutions externally,
   then the shared runner writes an incremental CSV row and, when enabled, a
   PostgreSQL row. Reference solutions may be used here for scoring, not as
   solver starts.
7. Solver exceptions, including `NoSolutionFoundError`, become result rows with
   `run_error`. CSV or PostgreSQL write failures remain fatal output-integrity
   failures.

## Benchmark Specs

| Spec | Category | Default solvers | Default time limits | Native columns |
| --- | --- | --- | --- | --- |
| `cvrp` | `list_variable` | `pyvrp`, `ortools`, `vroom`, `timefold`, `rustvrp`, `pyhygese`, `solverforge` | `1`, `10`, `60` | none |
| `employee-scheduling` | `scalar_variable` | `solverforge`, `timefold`, `ortools` | `1`, `10`, `60` | `nurses`, `weeks`, `validator_model_delta`, `score_drift` |
| `job-shop-scheduling` | `scalar_variable` | `solverforge`, `timefold`, `ortools` | `1`, `10`, `60` | `num_jobs`, `num_machines`, `num_operations`, `source_family`, `known_best_makespan`, `lower_bound_makespan`, `upper_bound_makespan`, `makespan_gap_to_best` |

## CVRP Adapter Shape

- Data lives under `list-variable/cvrp/data/X/` as CVRPLIB-X `.vrp` and `.sol`
  pairs.
- `spec.py` exposes dataset `CVRPLIB-X`, dataset set `canonical`, and
  `--num-instances` for smoke selection.
- `domain/models.py` defines Pydantic instance and solution contracts.
- `domain/utils.py` validates route feasibility and cost.
- `solver/solver.py` registers `pyvrp`, `ortools`, `vroom`, `timefold`,
  `rustvrp`, `pyhygese`, `solverforge`, and opt-in `solverforge-py`.
- Native solver builds are rooted in `solver/ortools/`, `solver/rustvrp/`,
  `solver/vroom/`, `solver/timefold/`, and `solver/solverforge/`.
- The SolverForge CVRP adapter is pinned to SolverForge `0.17.1` and resolves
  the sibling checkout at `../solverforge/crates/solverforge` from the
  repository root.
- The CVRP model uses public SolverForge CVRP list-variable hook bundles:
  `VrpSolution`, matrix distance meters, stock route hooks, stock savings
  depot/distance/metric-class hooks, and strict route feasibility for
  construction pruning. The benchmark budget is applied through the model
  config provider.
- The SolverForge and Timefold CVRP list variables start from empty route lists;
  adapter-owned incumbents, route hints, and reference-solution reads are not
  part of solver input.
- The `solverforge-py` CVRP adapter builds a public Python-binding list-variable
  model from the same CVRPLIB instance, starts all route lists empty, and
  reports the installed `solverforge` Python distribution version.
- `solverforge/solver.toml` uses reproducible mode, seed `42`, a 60 second
  internal termination cap, list construction phases, and a local-search union
  of nearby list moves, reverse moves, k-opt, ruin, and limited-neighborhood
  sublist change moves.
- Native OR-Tools no-solution exits are normalized to `NoSolutionFoundError`
  rather than benchmark-aborting runtime errors.
- Every CVRP wrapper emits a fair-start witness before solving. The native
  OR-Tools and SolverForge adapters also include native witness checks in their
  JSON output.

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
- `solver/solver.py` registers `solverforge`, opt-in `solverforge-py`,
  `timefold`, and `ortools`.
- The SolverForge NRP adapter is pinned to SolverForge `0.17.1` with `serde`
  enabled and resolves the sibling checkout at
  `../solverforge/crates/solverforge` from the repository root.
- The SolverForge NRP model uses public scalar APIs: per-shift candidate
  values, unassigned scalar variables for optional slots, nearby value/entity
  candidates, and one `ScalarGroup::assignment` for required minimum slots,
  one nurse per day capacity, adjacent forbidden-succession assignment rules,
  ordered shift positions, and nurse sequence keys.
- SolverForge initializes each shift with `nurse_idx = None`, Timefold leaves
  each `nurse` planning variable unset, and OR-Tools performs one CP-SAT solve
  without adapter hints, hard seeds, warm starts, or fallback schedules.
- The `solverforge-py` employee adapter builds a public Python-binding scalar
  model with unassigned `nurse_idx` variables. It encodes hard feasibility,
  public scalar assignment groups, indexed presence penalties, and shift-off
  request penalties; the shared validator remains the source of result
  feasibility and cost. This adapter is opt-in API coverage rather than a
  default performance row.
- The Python wrappers emit a witness before solving. SolverForge Rust counts
  preassigned scalar variables, Timefold Java counts preassigned `nurse`
  planning variables, and OR-Tools C++ inspects CP-SAT solution-hint fields in
  the native model proto.
- `solverforge_nrp/solver.toml` sets `environment_mode = "non_reproducible"`
  and `random_seed = 1`. It intentionally does not impose an independent
  termination cap; the shared harness passes the requested benchmark budget.

## Job-Shop Scheduling Adapter Shape

- Data lives under `scalar-variable/job-shop-scheduling/data/jsplib/` as bundled
  classic JSPLIB instance files sourced from `tamy0612/JSPLIB`.
- `manifest.json` defines dataset groups: `quick` has `ft06` and `la01`, and
  `canonical` has all 162 bundled JSPLIB instances across `abz`, `ft`, `la`,
  `orb`, `swv`, `ta`, and `yn`.
- `loader.py` parses standard JSPLIB text files with optional comments.
- `validation.py` is the shared Python referee. It checks operation coverage,
  job precedence, machine non-overlap, and returned makespan.
- `spec.py` exposes `--dataset-set` and `--datasets`, reports JSPLIB family,
  size, known optimum, lower/upper bounds, and makespan gap through native
  columns.
- `solver/solver.py` registers `solverforge`, opt-in `solverforge-py`,
  `timefold`, and `ortools`.
- The SolverForge JSSP adapter is pinned to SolverForge `0.17.1` and resolves
  the sibling checkout at `../solverforge/crates/solverforge`,
  `../solverforge/crates/solverforge-core`, and
  `../solverforge/crates/solverforge-scoring` from the repository root.
- Its list model declares each operation's fixed machine owner with
  `element_owner_fn`; SolverForge construction and list neighborhoods must not
  move an operation to a non-required machine.
- The SolverForge JSSP score path uses the stock upstream
  `ListPrecedenceMakespanConstraint`: job precedence is fixed precedence, each
  machine sequence contributes list precedence, missing/duplicate/wrong-owner
  assignments are hard penalties, and makespan is the soft objective. The
  adapter maps JSPLIB data into that generic constraint; it does not own a
  benchmark-local full-score search path.
- `solverforge_jssp/solver.toml` remains a stock SolverForge selector
  configuration. It may choose upstream list neighborhoods, but it does not add
  benchmark-local solver/search helpers, config probes, warm starts, or
  reference-solution hints.
- SolverForge and Timefold JSSP machine operation lists start empty. Known best
  bounds and validation data stay in specs and validators, not in solver-start
  incumbents.
- The `solverforge-py` JSSP adapter builds a public Python-binding list model
  with one empty machine sequence per machine and owner-constrained operation
  elements. The public first-class list precedence/makespan constraint scores
  operation ownership, assignment uniqueness, job precedence, machine order,
  and makespan; the shared validator remains the source of returned schedule
  feasibility and cost. This adapter is opt-in API coverage rather than a
  default performance row.
- The JSSP wrappers emit witnesses before solving. SolverForge Rust and
  Timefold Java count prefilled machine lists, and OR-Tools C++ records CP-SAT
  solution-hint counts from the model proto.

## Makefile Contract

- `make install-python-deps` creates or refreshes the root `.venv` and installs
  the sibling `../solverforge-py` package into it when that checkout is present.
- `make build-cvrp` builds Python dependencies plus CVRP Timefold, SolverForge,
  OR-Tools, rustvrp, and VROOM integrations.
- `make build-employee-scheduling` builds Python dependencies plus employee
  Timefold, SolverForge, and OR-Tools integrations.
- `make build-job-shop-scheduling` builds Python dependencies plus job-shop
  Timefold, SolverForge, and OR-Tools integrations.
- `make verify-fair-start` enforces that active solver adapters start from
  unassigned scalar variables or empty list variables, emit runtime witnesses,
  and do not read reference solutions or inject adapter-owned incumbents.
- `make verify-fair-start-rows RUN_ID=<uuid>` checks persisted PostgreSQL rows
  for valid fair-start witnesses after a DB smoke run.
- `make verify-stock-solverforge-guardrails` builds the active native adapters,
  runs stock SolverForge guardrail benchmarks, and parses the resulting CSVs.
  JSSP quick plus the fixed canonical subset must produce hard-feasible
  SolverForge rows with valid fair-start witnesses; CVRP and employee
  SolverForge smoke rows must remain hard-feasible with valid fair-start
  witnesses. Pass `--require-jssp-win` through `GUARDRAIL_ARGS` when the run
  should enforce that SolverForge ties or beats the best feasible JSSP solver
  row.
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
- `make bench-job-shop-scheduling-quick` runs `ft06` and `la01` at 1 and 10
  seconds with all registered job-shop solvers.
- `make bench-job-shop-scheduling-quick-db` runs the same job-shop smoke path
  after applying migrations and persists it to PostgreSQL.
- `make bench-job-shop-scheduling-solverforge-quick` runs the same quick
  job-shop slice with only SolverForge.
- `make bench-job-shop-scheduling-solverforge-quick-db` persists that same
  SolverForge-only job-shop smoke path after applying migrations.
- `make bench-cvrp`, `make bench-employee-scheduling`, and
  `make bench-job-shop-scheduling` run canonical benchmark paths at 1, 10, and
  60 seconds.
- `make bench-nightly-db` builds all benchmark stacks, applies migrations once,
  and invokes the root harness for CVRP, employee scheduling, and job-shop
  scheduling in parallel on their per-suite pinned cores.
- `make db-check`, `make db-create`, `make db-migrate`, and `make db-reset`
  operate on `DATABASE_URL`, then `BENCH_DATABASE_URL`, then
  `postgresql://postgres@localhost/solverforge_bench`.
- `make normalize-results` converts generated global CSV artifacts to normalized
  CSV or NDJSON through `scripts/normalize_results.py`.
- Benchmark run targets use per-suite pinned cores:
  `CVRP_BENCH_CPU ?= 0`, `EMPLOYEE_BENCH_CPU ?= 1`, and
  `JOBSHOP_BENCH_CPU ?= 2`. They set `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`,
  and per-core `BENCH_LOCK` values so different suites can run in parallel
  while accidental same-core runs serialize. `BENCH_CPU=<n>` intentionally
  forces all suites onto one core.
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
- `[benchmarks.job-shop-scheduling]` accepts `dataset_set` and `datasets`.
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
- Job-shop scheduling output defaults to
  `scalar-variable/job-shop-scheduling/data/benchmark_job_shop_scheduling_<stamp>.csv`.
- Employee scheduling solution artifacts are written under
  `scalar-variable/employee-scheduling/data/artifacts/employee_scheduling_<stamp>/`.
- Job-shop scheduling solution artifacts are written under
  `scalar-variable/job-shop-scheduling/data/artifacts/job_shop_scheduling_<stamp>/`.
- PostgreSQL stores run catalog rows in `benchmark_runs`, solver-version rows in
  `benchmark_solver_versions`, and result rows in `benchmark_results`.
- `benchmark_result_facts`, `latest_benchmark_runs`, and
  `latest_benchmark_result_facts` are the display-facing warehouse views.
- Completed result rows are written immediately. Interrupted runs keep partial
  rows but are excluded from latest-run views unless their run status is
  completed.

## CI Contract

- Python CI runs on `ubuntu-latest` in `.github/workflows/ci.yml` and on
  `python` runner labels in `.forgejo/workflows/ci.yml`.
- Rust CI runs on `ubuntu-latest` in `.github/workflows/ci.yml` and on `rust`
  runner labels in `.forgejo/workflows/ci.yml`.
- Python CI uses Python 3.14, creates the root `.venv` through
  `make install-python-deps HOST_PYTHON=...`, compiles Python source, parses
  benchmark TOML examples, validates bundled CVRP instances, and validates
  employee model parity. GitHub uses `actions/setup-python@v6`; Forgejo uses
  a shell Python 3.14 bootstrap because the local Forgejo action mirror does
  not provide that interpreter version.
- Rust CI clones SolverForge `main` into `$GITHUB_WORKSPACE/../solverforge`,
  the exact relative path declared by the active adapter `Cargo.toml` files. It
  checks formatting, runs
  `cargo clippy --locked --all-targets -- -D warnings`, and runs
  `cargo build --locked` for the CVRP SolverForge adapter, CVRP rustvrp
  adapter, employee SolverForge adapter, and job-shop SolverForge adapter.

## Generated Artifacts

- The ignored build and output surfaces are `.venv/`, `__pycache__/`, Python
  package/build outputs, Rust/Java `target/` outputs, `logs/*`, generated
  benchmark CSVs, and generated solution artifact directories.
- Generated CSVs are evidence artifacts. Commit them only when the run output is
  intentionally part of the change.
