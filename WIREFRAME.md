# SolverForge Bench Wireframe

This is the as-built map for the current benchmark repository. It is a
documentation contract: when source layout, benchmark ownership, run flow,
persistence, or CI changes, update this file with `README.md` and `AGENTS.md`.

## Root File Map

Every tracked file at the repository root and its role:

- `.gitignore` — ignores virtualenvs, caches, native build outputs, generated
  benchmark CSVs and artifacts, harness logs, and all dashboard runtime state
  (`dash/storage/`, `dash/log/`, `dash/tmp/`, `dash/config/master.key`).
- `.pre-commit-config.yaml` — local hooks: `check-yaml`, `end-of-file-fixer`,
  `trailing-whitespace`, `check-merge-conflict`, `check-added-large-files`,
  gitleaks secret detection, `black` and `ruff` for Python, and per-crate
  `cargo fmt`/`cargo clippy` hooks for the CVRP and employee-scheduling
  SolverForge crates.
- `AGENTS.md` — maintainer and agent contract: structure ownership, commands,
  testing gates, fairness rules, and publication rules.
- `README.md` — operator guide: setup, benchmark commands, configuration,
  persistence, result schema, dashboard usage.
- `WIREFRAME.md` — this as-built structure and data-flow map.
- `Makefile` — root build and execution surface (see Makefile Contract).
- `pyproject.toml` — Python 3.14 package `solverforge-bench` (version `0.1.0`),
  shared dependencies (`polars`, `pydantic`, `pyvrp`, `vrplib`, `hygese`,
  `psycopg[binary]`, exact `solverforge==0.6.10`), package discovery across the
  four source roots, and per-benchmark `solverforge_py.toml` package data.
- `benchmark.example.toml` — documents the TOML configuration surface with a
  minimal quick-run CVRP example.
- `benchmark.nightly.example.toml` — documents the combined nightly benchmark
  job configuration (canonical dataset sets, `run_kind = "candidate"`,
  `nightly = true`, PostgreSQL persistence enabled).
- `benchmark.nightly.toml` — tracked ready-to-use nightly configuration,
  currently identical to the example file.
- `docs_jssp_proposal.md` — design proposal that motivated the job-shop
  SolverForge list-variable adapter; historical design material.
- `JOB_SHOP_SOLVERFORGE_AUDIT.md` — audit record for the job-shop SolverForge
  adapter; historical review material.

## Repository Surfaces

- `src/solverforge_bench/` is the shared framework (see Shared Framework
  Modules). It owns CLI parsing, TOML loading, benchmark registry, exact run
  matrix construction and hashing, runtime artifact provenance, timed
  execution, watchdog containment, row construction, CSV writing, logging,
  solver output capture, solver-version collection, secret-safe command
  metadata, ETL, fair-start witnesses, SolverForge configuration parsing and
  failure classification, and optional PostgreSQL writes. Orchestration,
  timing, watchdog, CSV, TOML, logging, output-capture, and persistence policy
  live only here.
- `scripts/` holds the unified harness entrypoint, guardrail wrappers, and
  contract-test suites (see Scripts Map). Scripts bootstrap through
  `scripts/_venv_bootstrap.py` when they require the repository virtualenv.
- `list-variable/cvrp/` is the list-variable benchmark package for CVRP.
- `scalar-variable/employee-scheduling/` is the scalar-variable benchmark
  package for INRC-II nurse scheduling.
- `scalar-variable/job-shop-scheduling/` is the scalar-variable benchmark
  package for classic JSPLIB job-shop scheduling.
- `dash/` is the read-only Rails 8 benchmark dashboard (see Dashboard). It
  writes no benchmark rows and runs no warehouse migrations; Rails framework
  metadata (Solid Cache/Queue/Cable) stays in local SQLite under `dash/storage/`,
  which is runtime state and never committed.
- `migrations/` holds the SQLx-compatible PostgreSQL warehouse migration ledger
  (see Warehouse Schema and Migration Ledger).
- `.github/workflows/ci.yml` is the GitHub-hosted CI workflow.
- `.forgejo/workflows/ci.yml` is the local Forgejo CI workflow.
- `archive/` holds historical reports and older standalone scripts only
  (`benchmark_meeting_scheduling.py`, `benchmark_vehicle_routing.py`,
  `report.md`, `results_meeting-scheduling.md`, `results_vehicle-routing.md`,
  and `archive/README.md` marking the material historical). Not active source.
- `build/`, `logs/`, `.venv/`, caches, and `solverforge_bench.egg-info/` are
  untracked generated surfaces.

## Shared Framework Modules

Every module in `src/solverforge_bench/` and its single ownership:

| Module | Ownership |
| --- | --- |
| `cli.py` | CLI argument parsing, TOML load, benchmark selection, solver-name validation, run catalog finalization |
| `config.py` | Typed TOML configuration values (`values` + per-benchmark `benchmark_values`) |
| `registry.py` | Canonical benchmark spec registry: `cvrp`, `employee-scheduling`, `job-shop-scheduling` |
| `model.py` | Core dataclasses: `Evaluation`, `BenchmarkRow`, `SolverResult`, `FairStartWitness`, solver exception types (`NoSolutionFoundError`, `SolverExecutionError`, …), `BenchmarkRow.as_dict()` |
| `matrix.py` | Exact benchmark matrix construction and completion tracking (expected keys, hashes) |
| `runner.py` | Orchestration loop: case materialization, `case -> time_limit -> solver` iteration, row assembly, output completion attestation |
| `execution.py` | Timed solver execution in child processes; watchdog-only containment |
| `fair_start.py` | Fair-start witness construction, emission, and native-output witness parsing |
| `solver_versions.py` | Runtime solver-version collection (Cargo, Python distribution, Maven, executable hashing) |
| `solverforge_config.py` | Parses native/Python SolverForge TOML policy files and applies the termination-seconds overlay |
| `solverforge_failures.py` | Classifies SolverForge exceptions into `no_solution` vs `adapter_error` outcomes |
| `csv.py` | Incremental global snake_case CSV writing (`IncrementalCsvWriter`, column registry, `_csv_value` rendering) |
| `postgres.py` | Optional PostgreSQL run/result persistence, git state capture, command redaction on write |
| `redaction.py` | Redacts database URL values from command arguments before reporting or persistence |
| `logging.py` | Production logging policy and solver stdout/stderr capture |
| `etl.py` | Polars-based result ETL for `normalize_results.py` |
| `validation.py` | Shared validation helpers for benchmark run contracts (not the per-benchmark referees) |

## Scripts Map

| Script | Role |
| --- | --- |
| `run_benchmark.py` | Unified root harness entrypoint; bootstraps `.venv`, extends `sys.path` with all four source roots, delegates to `solverforge_bench.cli.main` |
| `_venv_bootstrap.py` | Shared virtualenv bootstrap helper for scripts that need the repo `.venv` |
| `verify_fair_start.py` | Static fair-start source checks over all active adapters; `--run-id` mode verifies persisted witness rows in PostgreSQL |
| `verify_solverforge_config_parity.py` | Parses each native/Python SolverForge TOML pair, requires semantic equality plus the qualified strongest-policy hash |
| `verify_benchmark_contracts.py` | Regression suite for exact matrix completion, runtime provenance, and SolverForge output-completeness boundaries (no solvers invoked) |
| `verify_solverforge_py_guardrails.py` | Release/local wrapper over the root harness: `solverforge-py` smoke slices, paired native/Python comparisons, production-scale one-second employee feasibility probe, CSV matrix validation, `summary.json` output |
| `verify_stock_solverforge_guardrails.py` | Stock SolverForge guardrail benchmarks and CSV parsing for the native adapters |
| `normalize_results.py` | Converts generated global CSV artifacts to normalized CSV or NDJSON through Polars |
| `reaudit_legacy_publication.py` | Re-audits legacy publication rows against current warehouse rules |
| `test_benchmark_contracts.py` | Test suite behind `make verify-benchmark-contracts` |
| `test_solver_output_contracts.py` | Test suite for SolverForge output-completeness classification |
| `test_verify_solverforge_py_guardrails.py` | Test suite behind `make verify-solverforge-py-guardrail-contract` |
| `test_reaudit_legacy_publication.py` | Test suite for the legacy publication re-audit |
| `test_git_provenance.py` | Test suite for the recorded source-tree provenance rule behind `git_dirty` |

## Shared Harness Flow

1. `scripts/run_benchmark.py` bootstraps into the root `.venv`, adds the four
   source roots to `sys.path`, and delegates to `solverforge_bench.cli.main`.
   Benchmark-local scripts such as
   `scalar-variable/employee-scheduling/scripts/verify_model_parity.py` use the
   same virtualenv bootstrap pattern.
2. `cli.py` loads optional TOML configuration, selects the benchmark spec,
   applies CLI overrides, finalizes run catalog fields, validates solver names,
   and passes the selected spec to `runner.py`.
3. `registry.py` exposes the canonical benchmark specs: `cvrp`,
   `employee-scheduling`, and `job-shop-scheduling`.
4. `runner.py` materializes a nonempty, duplicate-free case list, positive
   unique time limits, unique solvers, and the complete expected Cartesian
   matrix. It resolves content-hashed runtime provenance before opening output,
   then iterates `case -> time_limit -> solver` and refuses completion unless
   every expected key was emitted exactly once.
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
   failures. A SolverForge mandatory-construction stop at the requested time
   limit is a `no_solution` row with no objective and preserved native failure
   details; unrecognized SolverForge exceptions remain `adapter_error`.
8. `scripts/verify_solverforge_py_guardrails.py` is a release/local wrapper
   over the same root harness. It runs fixed `solverforge-py` smoke slices and
   paired native/Python comparison slices. Its one-second employee feasibility
   probe covers `n030w4`, `n050w8`, and `n080w8` and requires hard-feasible
   returned schedules. Before execution it resolves every requested dataset
   selector; afterward it requires the exact
   instance/time-limit/solver matrix, then writes
   `build/solverforge-py-guardrails/summary.json`. Database URL values are
   redacted from recorded commands and persisted run metadata.

## Benchmark Specs

| Spec | Category | Registered and default solvers | Default time limits | Native columns |
| --- | --- | --- | --- | --- |
| `cvrp` | `list_variable` | `pyvrp`, `ortools`, `vroom`, `timefold`, `rustvrp`, `pyhygese`, `solverforge`, `solverforge-py` | `1`, `10`, `60` | none |
| `employee-scheduling` | `scalar_variable` | `solverforge`, `solverforge-py`, `timefold`, `ortools` | `1`, `10`, `60` | `nurses`, `weeks`, `validator_model_delta`, `score_drift` |
| `job-shop-scheduling` | `scalar_variable` | `solverforge`, `solverforge-py`, `timefold`, `ortools` | `1`, `10`, `60` | `num_jobs`, `num_machines`, `num_operations`, `source_family`, `known_best_makespan`, `lower_bound_makespan`, `upper_bound_makespan`, `makespan_gap_to_best`, `makespan_gap_to_reference` |

## CVRP Adapter Shape

- Data lives under `list-variable/cvrp/data/X/` as 100 CVRPLIB-X `.vrp` and
  `.sol` pairs. Generated CVRP benchmark CSVs also land in that directory and
  are gitignored.
- `spec.py` exposes dataset `CVRPLIB-X`, dataset set `canonical`, and
  `--num-instances` for smoke selection.
- `domain/models.py` defines Pydantic instance and solution contracts.
- `domain/utils.py` validates route feasibility and cost.
- `main.py` is a tracked standalone inspection script that reads a single
  bundled `.vrp` file through `vrplib`; it is not part of the harness flow.
- `solver/solver.py` registers `pyvrp`, `ortools`, `vroom`, `timefold`,
  `rustvrp`, `pyhygese`, `solverforge`, and `solverforge-py`.
- Native solver builds are rooted in `solver/ortools/` (C++ Routing library
  executable with `PATH_CHEAPEST_ARC` + `GUIDED_LOCAL_SEARCH` and the time
  limit applied inside `RoutingSearchParameters`), `solver/rustvrp/`,
  `solver/vroom/`, `solver/timefold/` (Java, Timefold `2.7.0`), and
  `solver/solverforge/` (Rust/PyO3).
- The SolverForge CVRP manifest and committed registry lockfile target the
  published `0.19.8` crates.
- The CVRP model uses public SolverForge CVRP list-variable hook bundles:
  `VrpSolution`, matrix distance meters, stock route hooks, stock savings
  depot/distance/metric-class hooks, and strict route feasibility for
  construction pruning. The benchmark budget is applied through the model
  config provider.
- The SolverForge and Timefold CVRP list variables start from empty route lists;
  adapter-owned incumbents, route hints, and reference-solution reads are not
  part of solver input.
- The `solverforge-py` CVRP adapter builds a public Python-binding list-variable
  model from the same CVRPLIB instance. Its canonical `0.6.10` declaration uses
  independent `ListRouteHooks` and `ListSavingsHooks`, explicit row-scoped
  capacity/demand/distance metadata, and explicit cross/intra-position distance
  sources. It starts all route lists empty and reports the installed
  `solverforge` Python distribution version.
- `solverforge/solver.toml` uses reproducible mode, seed `42`, a 60 second
  internal termination cap, list construction phases, and a local-search union
  of nearby list moves, reverse moves, k-opt, ruin, and limited-neighborhood
  sublist change moves.
- `solverforge_py.toml` is the separate Python adapter copy of that complete
  policy. The adapter loads it directly and overlays only the requested
  termination seconds.
- Native OR-Tools no-solution exits are normalized to `NoSolutionFoundError`
  rather than benchmark-aborting runtime errors.
- Every CVRP wrapper emits a fair-start witness before solving. The native
  OR-Tools and SolverForge adapters also include native witness checks in their
  JSON output.

## Employee Scheduling Adapter Shape

- Data lives under `scalar-variable/employee-scheduling/data/inrc2/` as bundled
  INRC-II scenario, history, week-data, and reference solution TXT files, with
  `manifest.json` as the dataset catalog.
- `manifest.json` defines dataset groups: `quick` has 1 group and 3 cases,
  `test_with_solutions` has 3 groups and 9 cases, `canonical` has 14 groups and
  42 cases, and `late` has 6 groups and 18 cases.
- `loader.py` parses INRC-II TXT files and enumerates concrete cases.
- `validation.py` is the shared Python referee. It checks hard constraints
  first (single assignment per nurse-day, required skills, minimum coverage,
  forbidden successions) and then computes the soft-cost breakdown with fixed
  INRC-II weights (optimal coverage 30, shift-off requests 10, total
  assignment bounds 20, consecutive work/off bounds 30, consecutive shift-type
  bounds 15, working weekends 30, complete weekends 30). Every solver wrapper
  reports `hard_feasible` and `cost` from this validator, never from the
  solver's self-report.
- `scripts/verify_model_parity.py` verifies that the Python validator,
  OR-Tools model, Timefold model, and SolverForge model encode the same model
  contract (19 checked source clauses).
- `spec.py` exposes `--dataset-set` and `--datasets`, writes solution JSON
  artifacts for hard-feasible runs, and reports validator/model deltas through
  native columns. Clean evaluations persist `validation_error = NULL`; real
  hard-constraint violations persist the exception text.
- `solver/solver.py` registers `solverforge`, `solverforge-py`, `timefold`,
  and `ortools`. `instance_json.py` is the shared native-payload serializer
  that emits `optimal` shift slots per requirement with `is_minimum` flags.
- The SolverForge NRP manifest and committed registry lockfile target the
  published `0.19.8` crates with `serde` enabled.
- The SolverForge NRP model uses public scalar APIs: per-shift candidate
  values, unassigned scalar variables for optional slots, nearby value/entity
  candidates, and one `ScalarGroup::assignment` for required minimum slots,
  one nurse per day capacity, adjacent forbidden-succession assignment rules,
  ordered shift positions, and nurse sequence keys.
- SolverForge initializes each shift with `nurse_idx = None`, Timefold leaves
  each `nurse` planning variable unset, and OR-Tools performs one CP-SAT solve
  without adapter hints, hard seeds, warm starts, or fallback schedules.
  OR-Tools runs the default CP-SAT search portfolio with one worker and a
  fixed random seed for determinism; no decision strategy or fixed-search
  mode is imposed, so the greedy-fill misconfiguration that starved the
  solver of first incumbents is gone (retracted warehouse rows recorded it).
- The `solverforge-py` employee adapter builds a public Python-binding scalar
  model with unassigned `nurse_idx` variables. Immutable required, capacity,
  position, sequence, and same-nurse forbidden-succession conflict metadata
  stays in native row fields. The static conflict graph gives the assignment
  engine the same adjacency rule as the native Rust adapter without a Python
  callback on each candidate edge. Per-shift nurse candidates remain the native
  legality boundary for construction, swaps, and rematches, so an assignment
  cannot migrate onto a shift whose skill or initial-history domain excludes
  that nurse. Hard feasibility, indexed presence penalties, and shift-off
  request penalties remain in the constraint model; the shared validator
  remains the source of result feasibility and cost. This adapter is a
  first-class default performance row.
- The Python wrappers emit a witness before solving. SolverForge Rust counts
  preassigned scalar variables, Timefold Java counts preassigned `nurse`
  planning variables, and OR-Tools C++ inspects CP-SAT solution-hint fields in
  the native model proto.
- `solverforge_nrp/solver.toml` and `solverforge_py.toml` both set
  `random_seed = 1`. The native file sets `environment_mode =
  "non_reproducible"` and intentionally imposes no independent termination
  cap; the shared harness passes the requested benchmark budget. Both files
  omit explicit phases so both bindings select the same model-aware default
  construction and local-search profile. Timefold receives the budget through
  `TerminationConfig.spentLimit` inside the JVM; OR-Tools receives it through
  `SatParameters.max_time_in_seconds`.
- Timefold rejects nothing at the adapter boundary: hard-infeasible Timefold
  output at one-second budgets (JVM startup exceeds the budget) is an honest
  failed-solution row recorded by the shared validator, not a benchmark error.

## Job-Shop Scheduling Adapter Shape

- Data lives under `scalar-variable/job-shop-scheduling/data/jsplib/` as bundled
  classic JSPLIB instance files sourced from `tamy0612/JSPLIB`, with
  `manifest.json` as the dataset catalog.
- `manifest.json` defines dataset groups: `quick` has `ft06` and `la01`, and
  `canonical` has all 162 bundled JSPLIB instances across `abz` (5), `ft` (3),
  `la` (40), `orb` (10), `swv` (20), `ta` (80), and `yn` (4).
- `loader.py` parses standard JSPLIB text files with optional comments.
- `domain/models.py` defines Pydantic-serializable returned schedule models;
  `references.py` holds JSPLIB known-best, lower-bound, and upper-bound
  metadata used for scoring, never for solver starts.
- `validation.py` is the shared Python referee. It checks operation coverage,
  job precedence, machine non-overlap, and returned makespan.
- `spec.py` exposes `--dataset-set` and `--datasets`, reports JSPLIB family,
  size, known optimum, lower/upper bounds, and makespan gap through native
  columns.
- `solver/solver.py` registers `solverforge`, `solverforge-py`, `timefold`,
  and `ortools`. `instance_json.py` serializes the native payload.
- The SolverForge JSSP manifest and committed registry lockfile target the
  published SolverForge facade, SolverForge Core, and SolverForge Scoring
  `0.19.8` crates.
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
  reference-solution hints. `src/solverforge_bench/references.py` resolves
  every problem's official reference from the `references.json` beside its
  instances, and `scripts/generate_reference_catalog.py` regenerates each
  catalog from its published source (`make verify-reference-catalogs`).
- SolverForge and Timefold JSSP machine operation lists start empty. Known best
  bounds and validation data stay in specs and validators, not in solver-start
  incumbents.
- The `solverforge-py` JSSP adapter builds a public Python-binding list model
  with one empty machine sequence per machine and owner-constrained operation
  elements. The public first-class list precedence/makespan constraint scores
  operation ownership, assignment uniqueness, job precedence, machine order,
  and makespan; the shared validator remains the source of returned schedule
  feasibility and cost. This adapter is a first-class default performance row.
- The JSSP wrappers emit witnesses before solving. SolverForge Rust and
  Timefold Java count prefilled machine lists, and OR-Tools C++ records CP-SAT
  solution-hint counts from the model proto. The OR-Tools JSSP executable uses
  stock CP-SAT defaults with one worker and a fixed random seed.
- `solverforge_jssp/solver.toml` and the separate `solverforge_py.toml` both set
  `random_seed = 1` and omit explicit phases so native and Python use the same
  model-aware default construction and local-search profile.
- SolverForge Rust, SolverForge Python, and Timefold reject incomplete,
  duplicated, wrong-owner, or cyclic JSSP structure. They never replace an
  unknown operation start with zero.
- Both SolverForge CVRP adapters require every customer exactly once. Both
  employee-scheduling adapters require every callback-required shift while
  preserving optional unassigned shifts. Native adapters accept a solution
  only from `Completed`, never from a prior best after cancellation.

## Cross-Cutting Fairness, Witness, and Provenance Contract

- The only acceptable initial planning state is unassigned scalar variables or
  empty list variables. No adapter may receive or construct initial feasible
  schedules, incumbent hints, hard seeds as inputs, fallback schedules, warm
  starts, or reference solutions. Reference data lives only in specs,
  validators, parity scripts, demos, and result evaluation.
- Every solver wrapper emits a fair-start witness before invoking the solver;
  native adapters embed native witness checks in their JSON output. Witnesses
  are persisted per result row in PostgreSQL and re-verifiable with
  `make verify-fair-start-rows RUN_ID=<uuid>`.
- Runtime provenance hashes the actually invoked distribution, executable,
  native binary, or JAR; manifest declarations alone are not provenance. The
  per-solver pins are: native SolverForge `0.19.8` (CVRP, employee, job-shop,
  with committed registry lockfiles), Python `solverforge==0.6.10`,
  Timefold `2.7.0` (all three `pom.xml` files), OR-Tools `9.15.6755`
  (`ORTOOLS_VERSION` in the root Makefile).
- Native and Python SolverForge adapters keep separate configuration files per
  workload; `make verify-solverforge-config-parity` enforces semantic
  equality plus the qualified strongest-policy hash. The only per-run mutation
  is the same termination-seconds overlay on both paths.
- Determinism convention: every adapter pins its own random seed (`1` for the
  employee and job-shop pairs, `42` reproducible mode for CVRP native) and runs
  single-threaded; the harness has no seed plumbing by design.

## Dashboard

- `dash/` is a Rails 8.1 application (Ruby, `.ruby-version` `ruby-4.0.1`,
  Propshaft, importmap, Hotwire/Turbo/Stimulus, Thruster, Kamal deployment).
- It reads the PostgreSQL warehouse directly through the `pg` gem and is
  strictly read-only. `BENCH_DATABASE_URL` selects the warehouse; the root
  Makefile forwards its `DATABASE_URL` into the dash targets.
- Read-only models under `app/models/benchmark/` map one-to-one onto warehouse
  relations: `Run` -> `benchmark_runs`, `LatestRun` -> `latest_benchmark_runs`,
  `ResultFact` -> `benchmark_result_facts` (historical stream),
  `LatestResultFact` -> `latest_benchmark_result_facts` (current coherent
  snapshot), `SolverVersion` -> `benchmark_solver_versions`, plus `Result`,
  `Record` (base), `DashboardSnapshot`, `DashboardFilters`, and
  `FilterOptions`. The latest-vs-historical split is intentional: the
  warehouse view chooses completed runs first so a current dashboard is a
  coherent snapshot rather than a blend of partial runs.
- `app/controllers/dashboard_controller.rb` serves the single `index` view;
  `app/helpers/chart_helper.rb` renders chart data. `dash/docs/`
  `benchmark-warehouse.md` documents the warehouse contract from the
  dashboard side.
- Rails framework metadata (Solid Cache, Solid Queue, Solid Cable schemas)
  lives in local SQLite under `dash/storage/`; `db/cable_schema.rb`,
  `db/cache_schema.rb`, and `db/queue_schema.rb` declare those schemas. These
  are runtime state, never committed, and unrelated to warehouse migrations.
- `config/credentials.yml.enc` is tracked (encrypted); `config/master.key` is
  runtime state and never committed. `.kamal/secrets` pulls all values from
  the environment and is safe to track.
- The dashboard's own GitHub workflow was not imported; CI ownership belongs
  to this repository's workflows.

## Warehouse Schema and Migration Ledger

Migrations apply through `make db-migrate` (SQLx). In ledger order:

| Migration | Purpose |
| --- | --- |
| `20260512000000_create_benchmark_results.sql` | `benchmark_runs`, `benchmark_results`, core columns |
| `20260512001000_create_benchmark_result_views.sql` | `benchmark_result_facts`, `latest_benchmark_runs`, `latest_benchmark_result_facts` |
| `20260512002000_add_benchmark_run_status.sql` | run status enum and lifecycle columns |
| `20260512003000_add_benchmark_run_nightly.sql` | independent `nightly` flag |
| `20260512004000_add_benchmark_logging.sql` | log paths and solver output capture columns |
| `20260514000000_add_solver_versions.sql` | `benchmark_solver_versions` with runtime provenance metadata |
| `20260528000000_add_fair_start_witness.sql` | per-row fair-start witness and validity columns |
| `20260718000000_add_publication_integrity.sql` | expected-matrix catalog, SHA attestation columns, publication audit and `publishable_*` views |
| `20260904000000_add_official_reference_metrics.sql` | official job-shop reference metrics (known best, bounds, gaps) |
| `20261001000000_add_reference_catalog.sql` | `benchmark_reference_catalog` (official value, kind, source per instance) and `benchmark_reference_resolved` |
| `20260915203000_retract_misrepresenting_employee_runs.sql` | retracts employee-scheduling runs measured by superseded adapter versions or by the pre-fix OR-Tools employee binary; run-granularity deletion keeps exact-matrix attestation intact |

Tables:

- `benchmark_runs` — run catalog: benchmark name/category, solvers and time
  limits, command metadata (redacted), git commit and dirty flag, run kind,
  nightly flag, status (`running`/`completed`/`failed`), failure error,
  result counts, and the expected/observed matrix SHA-256 attestation pair.
- `benchmark_results` — one row per case/solver/time-limit with runtime
  (actual time, overshoot, watchdog), fair-start witness, error text,
  feasibility and cost fields (`hard_feasible`, `cost`, `reported_cost`,
  `fresh_cost`, `reference_cost`, `quality_ratio`), `validation_error`
  (NULL when validation passed), native-field JSON, `row_payload`, solver
  stdout/stderr paths, and the solver-version foreign key.
- `benchmark_run_matrix_entries` — the persisted expected
  case/solver/time-limit catalog per run.
- `benchmark_solver_versions` — one row per solver per run with the resolved
  version string, version source, and runtime artifact provenance metadata.

Views:

- Diagnostic: `benchmark_result_facts`, `latest_benchmark_runs`,
  `latest_benchmark_result_facts`.
- Publication: `benchmark_run_publication_audit` explains every rejected run
  with a failure array; `publishable_benchmark_runs`,
  `publishable_benchmark_result_facts`, `latest_publishable_benchmark_runs`,
  and `latest_publishable_benchmark_result_facts` are the only public
  publication surface. Publication requires a completed run from a clean,
  identified commit with an exact expected/observed matrix, valid fair-start
  witnesses, and complete runtime provenance. Solver failure rows are allowed
  inside an otherwise complete matrix.
- Source-tree provenance: `git_dirty` is true when tracked files differ from
  `HEAD` or untracked files exist under a harness source root (`src/`,
  `scripts/`, `list-variable/`, `scalar-variable/`); untracked runtime output
  elsewhere is recorded in `benchmark_runs.metadata.worktree` without failing
  the gate. `worktree_provenance()` in `src/solverforge_bench/postgres.py` owns
  the rule.

Referential behavior: `benchmark_results.run_id`,
`benchmark_run_matrix_entries.run_id`, and `benchmark_solver_versions.run_id`
cascade from `benchmark_runs`, so retraction migrations delete whole runs and
keep per-run attestation intact. Partial row deletion is never used.

## Makefile Contract

Virtualenv and validators:

- `make install-python-deps` creates or refreshes the root `.venv` and installs
  the exact published `solverforge==0.6.10` wheel.
- `make validate-cvrp` validates all bundled CVRP `.vrp`/`.sol` pairs.
- `make validate-job-shop-scheduling` validates the bundled JSPLIB manifest and
  parser output.
- `make validate-employee-model-parity` verifies that the employee-scheduling
  validator, OR-Tools model, Timefold model, and SolverForge model encode the
  same hard-feasibility clauses, candidate domains, and soft objective weights.

Builds:

- `make build-cvrp` builds Python dependencies plus CVRP Timefold, SolverForge,
  OR-Tools, rustvrp, and VROOM integrations.
- `make build-employee-scheduling` builds Python dependencies plus employee
  Timefold, SolverForge, and OR-Tools integrations.
- `make build-job-shop-scheduling` builds Python dependencies plus job-shop
  Timefold, SolverForge, and OR-Tools integrations.

Contract gates:

- `make verify-fair-start` enforces that active solver adapters start from
  unassigned scalar variables or empty list variables, emit runtime witnesses,
  and do not read reference solutions or inject adapter-owned incumbents.
- `make verify-fair-start-rows RUN_ID=<uuid>` checks persisted PostgreSQL rows
  for valid fair-start witnesses after a DB smoke run.
- `make verify-benchmark-contracts` exercises exact matrix completion, runtime
  provenance, and all SolverForge output-completeness boundaries without
  running a full benchmark suite.
- `make verify-solverforge-config-parity` parses each separate native/Python
  TOML pair, requires semantic equality, and pins the result to the qualified
  strongest-policy hash so jointly weakening both copies also fails.
- `make verify-stock-solverforge-guardrails` builds the active native adapters,
  runs stock SolverForge guardrail benchmarks, and parses the resulting CSVs.
  Pass `--require-jssp-win` through `GUARDRAIL_ARGS` to enforce that
  SolverForge ties or beats the best feasible JSSP solver row.
- `make verify-solverforge-py-smoke` builds the native SolverForge adapters,
  verifies fair-start source checks, runs `solverforge-py` smoke rows through
  the shared harness, and parses the generated CSVs. Its production-scale
  one-second feasibility probe covers `n030w4`, `n050w8`, and `n080w8`.
- `make verify-solverforge-py-guardrail-contract` runs the focused exact-matrix
  and command-redaction regression suite without invoking solvers.
- `make verify-solverforge-py-comparison` runs paired native `solverforge` and
  `solverforge-py` rows through the shared harness and records parsable
  quality and wall-time summaries without PostgreSQL by default.
- `make verify-solverforge-py-release` combines compileall, benchmark
  validators, fair-start checks, native adapter builds, smoke, and paired
  comparison into one release-mode guardrail invocation and summary.

Benchmark runs:

- Quick slices: `make bench-cvrp-quick` (three CVRP instances at 1s and 10s,
  all registered CVRP solvers), `make bench-employee-scheduling-quick`
  (`n005w4` at 1s and 10s, all four solvers), `make
  bench-job-shop-scheduling-quick` (`ft06` and `la01` at 1s and 10s, all four
  solvers); the `-db` variants apply migrations and persist to PostgreSQL; the
  `-solverforge-quick` and `-solverforge-quick-db` variants restrict to
  SolverForge.
- Canonical paths: `make bench-cvrp`, `make bench-employee-scheduling`, and
  `make bench-job-shop-scheduling` run at 1, 10, and 60 seconds, with `-db`
  and SolverForge-only variants.
- `make bench-nightly-db` builds all benchmark stacks, applies migrations once,
  and invokes the root harness for all three benchmarks in parallel on their
  per-suite pinned cores.
- Per-suite pinned cores: `CVRP_BENCH_CPU ?= 0`, `EMPLOYEE_BENCH_CPU ?= 1`,
  `JOBSHOP_BENCH_CPU ?= 2`, with `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, and
  per-core `BENCH_LOCK` values. `BENCH_CPU=<n>` intentionally forces all
  suites onto one core.
- Override child harness arguments with `BENCH_ARGS`, nightly child arguments
  with `NIGHTLY_ARGS`, config path with `BENCH_CONFIG`, and SQLx reset flags
  with `DB_RESET_FLAGS`.

Warehouse and artifacts:

- `make db-check`, `make db-create`, `make db-migrate`, and `make db-reset`
  operate on `DATABASE_URL`, then `BENCH_DATABASE_URL`, then
  `postgresql://postgres@localhost/solverforge_bench`.
- `make normalize-results` converts generated global CSV artifacts to normalized
  CSV or NDJSON through `scripts/normalize_results.py`.

Dashboard:

- `make dash-setup`, `make dash-server`, `make dash-warehouse-check`,
  `make dash-smoke`, and `make dash-test` delegate to `dash/Makefile` with the
  root warehouse URL. The dash Makefile additionally exposes `install`,
  `dev`, `console`, `routes`, `db-prepare`, `db-reset`, `lint`, `security`,
  `audit`, `ci-local`, `clean`, and `logs-clear`/`tmp-clear` maintenance
  targets.

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
- The root harness reads `BENCH_CONFIG` or `--config`; command-line options
  override TOML values. `make bench-nightly-db` defaults to
  `benchmark.nightly.example.toml`; `NIGHTLY_ARGS` containing `--config`
  overrides that selection.

## Output And Persistence

- CSV output uses one global snake_case schema with stable optional native
  columns; clean rows render `validation_error` as a blank field.
- `BenchmarkRow.as_dict()` emits core fields and merges native fields.
- CVRP output defaults to `list-variable/cvrp/data/benchmark_cvrp_<stamp>.csv`.
- Employee scheduling output defaults to
  `scalar-variable/employee-scheduling/data/benchmark_employee_scheduling_<stamp>.csv`.
- Job-shop scheduling output defaults to
  `scalar-variable/job-shop-scheduling/data/benchmark_job_shop_scheduling_<stamp>.csv`.
- Harness logs (run log plus per-solver stdout/stderr captures) are written
  under `logs/<benchmark>_<stamp>/`.
- SolverForge-Py guardrail CSVs, logs, and `summary.json` are written under
  `build/solverforge-py-guardrails/` by the wrapper. Benchmark-local solution
  artifact writing remains shared harness behavior and uses the spec artifact
  directories.
- Employee scheduling solution artifacts are written under
  `scalar-variable/employee-scheduling/data/artifacts/employee_scheduling_<stamp>/`.
- Job-shop scheduling solution artifacts are written under
  `scalar-variable/job-shop-scheduling/data/artifacts/job_shop_scheduling_<stamp>/`.
- PostgreSQL persistence writes rows immediately as each result completes;
  interrupted runs keep partial rows but stay excluded from latest-run views
  unless their run status is `completed`.

## CI Contract

- Python CI runs on `ubuntu-latest` in `.github/workflows/ci.yml` (GitHub
  Python Harness job) and on `python` runner labels in
  `.forgejo/workflows/ci.yml` (Forgejo Python Harness job). It uses Python
  3.14, creates the root `.venv` through
  `make install-python-deps HOST_PYTHON=...`, compiles Python source with
  `compileall -q` over `src`, `list-variable/cvrp/src`,
  `scalar-variable/employee-scheduling/src`,
  `scalar-variable/job-shop-scheduling/src`, and `scripts`, parses the
  benchmark TOML examples, verifies SolverForge config parity, the shared
  matrix/provenance contract (`verify-benchmark-contracts`), the Python
  guardrail regression contract, the fair-start witness contract, validates
  bundled CVRP instances, and validates employee model parity. GitHub uses
  `actions/setup-python@v6`; Forgejo bootstraps Python 3.14 from the runner
  because the local Forgejo action mirror does not provide that interpreter.
- Rust CI runs on `ubuntu-latest` in `.github/workflows/ci.yml` (GitHub Rust
  Adapters job) and on `rust` runner labels in `.forgejo/workflows/ci.yml`
  (Forgejo Rust Adapters job). It preserves strict `--locked` resolution,
  checks formatting, runs
  `cargo clippy --locked --all-targets -- -D warnings`, and runs
  `cargo build --locked` for the CVRP SolverForge adapter, CVRP rustvrp
  adapter, employee SolverForge adapter, and job-shop SolverForge adapter.
  Adapter manifests and committed locks target SolverForge `0.19.8`.
- The dashboard has no CI jobs yet; adding Rails checks to both workflows is
  the known follow-up.

## Generated Artifacts

- The ignored build and output surfaces are `.venv/`, `__pycache__/`, Python
  package/build outputs, Rust/Java `target/` outputs, `logs/*`, generated
  benchmark CSVs, `build/solverforge-py-guardrails/`, generated solution
  artifact directories, and dashboard runtime state (`dash/storage/`,
  `dash/log/`, `dash/tmp/`, `dash/config/master.key`).
- Generated CSVs are evidence artifacts. Commit them only when the run output is
  intentionally part of the change.
