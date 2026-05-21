# Repository Guidelines

## Project Structure & Module Organization

- `pyproject.toml` declares shared Python dependencies and package discovery.
- `README.md` is the operator guide. `WIREFRAME.md` is the as-built
  repository/data-flow map. Keep both aligned with this file when public
  behavior or structure changes.
- `.github/workflows/ci.yml` contains the split GitHub/Forgejo CI workflow.
  Keep its sibling SolverForge checkout paths aligned with the active adapter
  `Cargo.toml` path dependencies. The Rust jobs must clone SolverForge
  `v0.14.1` into `../solverforge`, clone `feat/node-sharing-compiler` into
  `../solverforge-node-sharing`, and run Cargo checks with `--locked`; the
  Python jobs must create the root `.venv` with `make install-python-deps`
  before parity validation.
- `src/solverforge_bench/` contains the shared benchmark framework. CLI,
  TOML configuration, registry, run matrix, timing, overshoot calculation,
  watchdog containment, result rows, CSV writing, production logging, solver
  stdout/stderr capture, and optional PostgreSQL persistence belong here, not
  in problem-specific scripts.
- `migrations/` contains SQLx-compatible PostgreSQL migrations for benchmark
  warehouse tables and display views.
- `benchmark.example.toml` documents the current TOML configuration surface for
  shared run settings, benchmark-specific filters, and PostgreSQL options.
- `benchmark.nightly.example.toml` documents the combined nightly benchmark job
  configuration.
- `list-variable/cvrp/` contains the canonical CVRP benchmark imported from `~/hack/cvrp_solver_comparison`, with source in `src/cvrp_bench/` and instances under `data/X/`.
- `scalar-variable/employee-scheduling/` contains the nurse rostering benchmark, with source in `src/employee_scheduling_bench/` and INRC2 datasets under `data/inrc2/`.
- `archive/` holds previous reports and older standalone scripts; do not treat it as active source.

## Build, Test, and Development Commands

- `python3.14 -m venv .venv && . .venv/bin/activate && pip install -e .`
  creates the single repository virtualenv used by all benchmark commands.
- `make install-python-deps` creates or refreshes that root `.venv` from the
  Makefile.
- The CVRP SolverForge adapter is pinned to SolverForge `0.14.1` and currently
  uses the sibling checkout at `../solverforge/crates/solverforge`. The
  employee-scheduling SolverForge adapter uses the `0.15.0` node-sharing
  compiler branch at `../solverforge-node-sharing/crates/solverforge`.
- Benchmark run targets pin the shared harness with `taskset -c $(BENCH_CPU)`;
  `BENCH_CPU` defaults to `0`. They also set `OMP_NUM_THREADS=1` and
  `MKL_NUM_THREADS=1`.
- `make validate-cvrp` validates all bundled CVRP `.vrp`/`.sol` pairs.
- `make build-cvrp` builds Python dependencies plus CVRP Timefold, SolverForge,
  OR-Tools, rustvrp, and VROOM integrations.
- `make bench-cvrp-quick` builds CVRP native integrations and runs a small sample.
  It uses all registered CVRP solvers.
- `make bench-cvrp-quick-db` does the same quick CVRP run, applies database
  migrations first, and persists the run to PostgreSQL.
- `make bench-cvrp-solverforge-quick` runs only SolverForge CVRP on three instances with 1s and 10s limits.
- `make bench-cvrp-solverforge-quick-db` persists that same SolverForge-only
  CVRP smoke path after applying migrations.
- `make build-employee-scheduling` builds Python dependencies plus employee
  Timefold, SolverForge, and OR-Tools integrations.
- `make bench-employee-scheduling-quick` runs a small INRC2 sample.
- `make bench-employee-scheduling-quick-db` does the same quick
  employee-scheduling run, applies database migrations first, and persists the
  run to PostgreSQL.
- `make bench-employee-scheduling-solverforge-quick` runs only SolverForge on
  the same quick employee-scheduling sample.
- `make bench-employee-scheduling-solverforge-quick-db` persists that same
  SolverForge-only employee-scheduling smoke path after applying migrations.
- `make bench-nightly-db` is the cronable nightly entrypoint: it builds both
  benchmark stacks, applies migrations once, then invokes the canonical root
  harness directly for CVRP and employee scheduling. It uses
  `benchmark.nightly.example.toml` by default and persists both runs to
  PostgreSQL.
- `make validate-employee-model-parity` verifies that the employee-scheduling
  validator, OR-Tools model, Timefold model, and SolverForge model encode
  the same hard-feasibility clauses, candidate domains, and soft objective
  weights.
- `make bench-cvrp` and `make bench-employee-scheduling` run the broader benchmark suites and may take longer.
- `make db-check`, `make db-create`, `make db-migrate`, and `make db-reset`
  check, create, migrate, and reset the PostgreSQL benchmark warehouse
  configured by `DATABASE_URL`, or `BENCH_DATABASE_URL` when `DATABASE_URL` is
  unset. The default URL is `postgresql://postgres@localhost/solverforge_bench`.
  `make db-reset` passes `DB_RESET_FLAGS ?= -y -f` to SQLx by default.
- `make normalize-results INPUT=... OUTPUT=...` normalizes generated global CSV
  artifacts through Polars. Pass `ARGS="--format ndjson"` for NDJSON output.
- `PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src .venv/bin/python3 scripts/run_benchmark.py <benchmark>` runs the unified root harness directly.
- Add `--config benchmark.example.toml` or `BENCH_CONFIG=benchmark.example.toml`
  to load TOML configuration. Command-line options override TOML values.
- Use `--run-kind quick|candidate|tag` for benchmark classification. `tag`
  requires `--release-tag`. Use `--nightly` independently for scheduled cron
  runs; nightly runs can be quick, candidate, or tag runs.
- Use `--log-level`, `--log-dir`, `--log-file`,
  `--show-solver-output|--no-show-solver-output`, and
  `--capture-solver-output|--no-capture-solver-output` for logging behavior.
  Logging policy belongs to `src/solverforge_bench/`, not to benchmark adapters.
- Use `BENCH_ARGS` to append child harness options to normal benchmark Make
  targets. Use `NIGHTLY_ARGS` for `make bench-nightly-db`; if `NIGHTLY_ARGS`
  includes `--config`, it overrides the Makefile's nightly config selection.

## Coding Style & Naming Conventions

Use 4-space indentation, `snake_case` functions and modules, and type hints where they clarify benchmark contracts. In CVRP, keep domain models in `domain/models.py`, validation in `domain/utils.py`, and solver adapters in `solver/<name>.py`. In employee scheduling, keep loaders in `loader.py`, validation in `validation.py`, and solver adapters in `solver/<name>.py`. Adapter names should match CLI arguments such as `solverforge`, `pyvrp`, `timefold`, or `ortools`.

## Testing Guidelines

There is no dedicated pytest suite. Treat quick benchmark targets and validation
scripts as smoke tests. For CVRP, run `make validate-cvrp` plus one quick
benchmark target. For employee scheduling, run
`make bench-employee-scheduling-quick`. For PostgreSQL or run-catalog changes,
also run `make db-migrate` and at least one `*-db` dry run or smoke run. When
adding a dataset or solver, include a small deterministic run and confirm
failures are solution failures, not loader or adapter errors.

For CI or documentation contract changes, also verify Python syntax with
`python -m compileall -q src list-variable/cvrp/src scalar-variable/employee-scheduling/src scripts`
and parse `benchmark*.toml` with `tomllib` or an equivalent TOML parser.

## Commit & Pull Request Guidelines

Use concise Conventional Commit subjects, for example `docs: add contributor guide` or `fix: correct cvrp validation`, with a body when behavior or interpretation changes. Pull requests should describe the scenario, commands run, generated files, and solver/runtime assumptions. Avoid committing generated CSVs unless they are intentional evidence artifacts.

## Agent-Specific Instructions

Keep changes tightly scoped. For documentation-only requests, update
documentation only; do not modify solver adapters, benchmark runner behavior,
generated result handling, CI, or build flow. When the request names
`README.md`, `AGENTS.md`, or wireframes, include root `README.md`, root
`AGENTS.md`, root `WIREFRAME.md`, and any additional tracked `WIREFRAME.md` or
`wireframe.md` files in the audit. For benchmark execution changes, preserve one
shared framework: problem adapters may load data, create solvers,
validate/evaluate solutions, and expose native fields, but must not own
orchestration loops, timing policy, watchdog policy, CSV policy, TOML
configuration policy, logging policy, solver-output capture policy, or
PostgreSQL persistence policy. The nominal benchmark budget is not a hard kill
deadline; preserve late returned solutions and record overshoot. Only the
separate watchdog may terminate runaway processes.

Do not reintroduce `standard-variable`, `CoverageGroup`, `coverage_first_fit`,
or benchmark-local scoring internals for employee scheduling. The active
terminology is `scalar-variable/employee-scheduling`, and the active SolverForge
adapter uses public SolverForge scalar/list APIs.
