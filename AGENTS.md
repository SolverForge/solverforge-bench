# Repository Guidelines

## Project Structure & Module Organization

- `pyproject.toml` declares shared Python dependencies and package discovery.
- `README.md` is the operator guide. `WIREFRAME.md` is the as-built
  repository/data-flow map. Keep both aligned with this file when public
  behavior or structure changes.
- `.github/workflows/ci.yml` contains the GitHub-hosted CI workflow.
  `.forgejo/workflows/ci.yml` contains the local Forgejo CI workflow. Keep
  the exact SolverForge registry versions and committed adapter lockfiles
  aligned. The Rust jobs run Cargo checks with `--locked`; the Python jobs must
  create the root `.venv` with `make install-python-deps` before parity
  validation.
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
- `scalar-variable/job-shop-scheduling/` contains the JSPLIB job-shop
  scheduling benchmark, with source in `src/job_shop_bench/`, instances under
  `data/jsplib/`, a SolverForge Rust/PyO3 adapter under
  `solver/solverforge_jssp/`, a Timefold Java adapter under `solver/timefold/`,
  and an OR-Tools C++ CP-SAT adapter under `solver/ortools/`.
- `archive/` holds previous reports and older standalone scripts; do not treat it as active source.

## Build, Test, and Development Commands

- `python3.14 -m venv .venv && . .venv/bin/activate && pip install -e .`
  creates the single repository virtualenv used by all benchmark commands.
- `make install-python-deps` creates or refreshes that root `.venv` from the
  Makefile.
- The CVRP, employee-scheduling, and job-shop native SolverForge adapters are
  pinned to the published SolverForge `0.18.0` crates. The `solverforge-py`
  adapters use the exact published `solverforge==0.6.1` Python wheel.
- Benchmark run targets pin the shared harness with per-suite CPU defaults:
  `CVRP_BENCH_CPU ?= 0`, `EMPLOYEE_BENCH_CPU ?= 1`, and
  `JOBSHOP_BENCH_CPU ?= 2`. They also set `OMP_NUM_THREADS=1`,
  `MKL_NUM_THREADS=1`, and per-core `BENCH_LOCK` values so different suites can
  run in parallel while accidental same-core runs serialize. `BENCH_CPU=<n>`
  intentionally forces all suites onto one core.
- `make validate-cvrp` validates all bundled CVRP `.vrp`/`.sol` pairs.
- `make build-cvrp` builds Python dependencies plus CVRP Timefold, SolverForge,
  OR-Tools, rustvrp, and VROOM integrations.
- `make bench-cvrp-quick` builds CVRP native integrations, installs the exact
  SolverForge Python binding release, and runs a small sample. It uses the
  default CVRP solver set, including both native `solverforge` and
  `solverforge-py`.
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
- `make validate-job-shop-scheduling` validates the bundled JSPLIB manifest and
  parser output.
- `make build-job-shop-scheduling` builds the SolverForge JSSP Python extension,
  the Timefold JSSP fat JAR, and the native OR-Tools JSSP executable.
- `make bench-job-shop-scheduling-quick` runs the JSPLIB quick group for
  `solverforge`, `solverforge-py`, `timefold`, and `ortools` at 1s and 10s
  limits.
- `make bench-job-shop-scheduling-quick-db` does the same quick
  job-shop-scheduling run, applies database migrations first, and persists the
  run to PostgreSQL.
- `make bench-nightly-db` is the cronable nightly entrypoint: it builds all
  benchmark stacks, applies migrations once, then invokes the canonical root
  harness directly for CVRP, employee scheduling, and job-shop scheduling. It
  uses `benchmark.nightly.example.toml` by default and persists all runs to
  PostgreSQL.
- `make validate-employee-model-parity` verifies that the employee-scheduling
  validator, OR-Tools model, Timefold model, and SolverForge model encode
  the same hard-feasibility clauses, candidate domains, and soft objective
  weights.
- `make bench-cvrp`, `make bench-employee-scheduling`, and
  `make bench-job-shop-scheduling` run the broader benchmark suites and may
  take longer.
- `make db-check`, `make db-create`, `make db-migrate`, and `make db-reset`
  check, create, migrate, and reset the PostgreSQL benchmark warehouse
  configured by `DATABASE_URL`, or `BENCH_DATABASE_URL` when `DATABASE_URL` is
  unset. The default URL is `postgresql://postgres@localhost/solverforge_bench`.
  `make db-reset` passes `DB_RESET_FLAGS ?= -y -f` to SQLx by default.
- `make normalize-results INPUT=... OUTPUT=...` normalizes generated global CSV
  artifacts through Polars. Pass `ARGS="--format ndjson"` for NDJSON output.
- `PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src .venv/bin/python3 scripts/run_benchmark.py <benchmark>` runs the unified root harness directly.
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

Use 4-space indentation, `snake_case` functions and modules, and type hints
where they clarify benchmark contracts. In CVRP, keep domain models in
`domain/models.py`, validation in `domain/utils.py`, and solver adapters in
`solver/<name>.py`. In employee scheduling, keep loaders in `loader.py`,
validation in `validation.py`, and solver adapters in `solver/<name>.py`. In
job-shop scheduling, keep the JSPLIB loader in `loader.py`, strict schedule
validation in `validation.py`, Pydantic-serializable returned schedule models in
`domain/models.py`, the solver registry in `solver/solver.py`, and native
solver implementations under their adapter directories. Adapter names should
match CLI arguments such as `solverforge`, `pyvrp`, `timefold`, or `ortools`.

## Testing Guidelines

There is no dedicated pytest suite. Treat quick benchmark targets and validation
scripts as smoke tests. For CVRP, run `make validate-cvrp` plus one quick
benchmark target. For employee scheduling, run
`make bench-employee-scheduling-quick`. For job-shop scheduling, run
`make validate-job-shop-scheduling` plus `make bench-job-shop-scheduling-quick`
or a focused root harness run with `--solver` when only one adapter changed. For
PostgreSQL or run-catalog changes, also run `make db-migrate` and at least one
`*-db` dry run or smoke run. When adding a dataset or solver, include a small
deterministic run and confirm failures are solution failures, not loader or
adapter errors.

For CI or documentation contract changes, also verify Python syntax with
`python -m compileall -q src list-variable/cvrp/src scalar-variable/employee-scheduling/src scalar-variable/job-shop-scheduling/src scripts`,
run `make verify-fair-start`, run `make verify-solverforge-config-parity`, and
parse `benchmark*.toml` with `tomllib` or an equivalent TOML parser.

After changing `solverforge-py` adapters, Python-binding runtime behavior, or
benchmark fairness logic, run `make install-python-deps`,
`make verify-fair-start`, `make verify-solverforge-config-parity`, and
`make verify-solverforge-py-guardrail-contract`, then
`make verify-solverforge-py-smoke`. Before a release or public benchmark claim,
also run
`make verify-solverforge-py-comparison`. Do not run `make bench-nightly-db` for
this gate unless explicitly requested, and do not commit generated guardrail
CSV, log, summary, or solution artifact files.

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

Benchmark fairness is part of the architecture, not an optional benchmark knob.
Solvers must not receive or construct adapter-owned initial feasible schedules,
incumbent hints, hard seeds, fallback schedules, warm starts, or reference
solutions. The only acceptable initial planning state is unassigned scalar
variables or empty list variables. Every solver wrapper must return
`SolverResult`, emit a fair-start witness before invoking the actual solver, and
keep native witness checks aligned with the underlying adapter. Reference
solutions belong only in specs, validators, parity scripts, demos, and result
evaluation. Run `make verify-fair-start` when editing solver adapters, solver
specs, validators, benchmark CI, or benchmark architecture docs. For persisted
smoke runs, also run `make verify-fair-start-rows RUN_ID=<uuid>` so PostgreSQL
rows prove the runtime contract, not only the static source shape.

Native and Python SolverForge adapters keep separate configuration files for
each workload. Their parsed policies must remain semantically identical and
must retain the qualified strongest-policy hash enforced by
`make verify-solverforge-config-parity`; do not weaken one adapter to make a
comparison look equal, and do not weaken both copies to satisfy parity. The
only per-run mutation is the same termination-seconds overlay on both paths.

SolverForge Python guardrails must fail before execution when any requested
dataset selector resolves to no instance. Their CSV validation must require the
exact requested instance/time-limit/solver matrix, including whole keys for
which neither solver emitted a row. Commands stored in summaries, errors, or
PostgreSQL run metadata must redact database URL values while execution still
uses the real URL.

Do not reintroduce `standard-variable`, `CoverageGroup`, `coverage_first_fit`,
or benchmark-local scoring internals for employee scheduling. The active
terminology is `scalar-variable/employee-scheduling`, and the active SolverForge
adapter uses public SolverForge scalar/list APIs.
