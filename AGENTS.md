# Repository Guidelines

## Project Structure & Module Organization

- `pyproject.toml` declares shared Python dependencies and package discovery.
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
- `make validate-cvrp` validates all bundled CVRP `.vrp`/`.sol` pairs.
- `make bench-cvrp-quick` builds CVRP native integrations and runs a small sample.
  It uses all registered CVRP solvers.
- `make bench-cvrp-quick-db` does the same quick CVRP run, applies database
  migrations first, and persists the run to PostgreSQL.
- `make bench-cvrp-solverforge-quick` runs only SolverForge CVRP on three instances with 1s and 10s limits.
- `make bench-employee-scheduling-quick` runs a small INRC2 sample.
- `make bench-employee-scheduling-quick-db` does the same quick
  employee-scheduling run, applies database migrations first, and persists the
  run to PostgreSQL.
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
- `make db-check`, `make db-create`, and `make db-migrate` check, create, and
  migrate the PostgreSQL benchmark warehouse configured by `DATABASE_URL`, or
  `BENCH_DATABASE_URL` when `DATABASE_URL` is unset. The default URL is
  `postgresql://postgres@localhost/solverforge_bench`.
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

## Commit & Pull Request Guidelines

Use concise Conventional Commit subjects, for example `docs: add contributor guide` or `fix: correct cvrp validation`, with a body when behavior or interpretation changes. Pull requests should describe the scenario, commands run, generated files, and solver/runtime assumptions. Avoid committing generated CSVs unless they are intentional evidence artifacts.

## Agent-Specific Instructions

Keep changes tightly scoped. For documentation-only requests, update
documentation only; do not modify solver adapters, benchmark runner behavior,
generated result handling, or build flow. For benchmark execution changes,
preserve one shared framework: problem adapters may load data, create solvers,
validate/evaluate solutions, and expose native fields, but must not own
orchestration loops, timing policy, watchdog policy, CSV policy, TOML
configuration policy, logging policy, solver-output capture policy, or
PostgreSQL persistence policy. The nominal benchmark budget is not a hard kill
deadline; preserve late returned solutions and record overshoot. Only the
separate watchdog may terminate runaway processes.
