# Repository Guidelines

## Project Structure & Module Organization

- `pyproject.toml` declares shared Python dependencies and package discovery.
- `src/solverforge_bench/` contains the shared benchmark framework. CLI,
  registry, run matrix, timing, overshoot calculation, watchdog containment,
  result rows, and CSV writing belong here, not in problem-specific scripts.
- `list-variable/cvrp/` contains the canonical CVRP benchmark imported from `~/hack/cvrp_solver_comparison`, with source in `src/cvrp_bench/` and instances under `data/X/`.
- `scalar-variable/employee-scheduling/` contains the nurse rostering benchmark, with source in `src/employee_scheduling_bench/` and INRC2 datasets under `data/inrc2/`.
- `archive/` holds previous reports and older standalone scripts; do not treat it as active source.

## Build, Test, and Development Commands

- `cd list-variable/cvrp && python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ../..` creates the CVRP virtualenv used by the full script.
- `make validate-cvrp` validates all bundled CVRP `.vrp`/`.sol` pairs.
- `make bench-cvrp-quick` builds CVRP native integrations and runs a small sample.
- `make bench-cvrp-solverforge-quick` runs only SolverForge CVRP on three instances with 1s and 10s limits.
- `make bench-employee-scheduling-quick` runs a small INRC2 sample.
- `make validate-employee-model-parity` verifies that the employee-scheduling
  validator, OR-Tools model, Timefold Java model, and SolverForge model encode
  the same hard-feasibility clauses, candidate domains, and soft objective
  weights.
- `make bench-cvrp` and `make bench-employee-scheduling` run the broader benchmark suites and may take longer.
- `PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src python3.12 scripts/run_benchmark.py <benchmark>` runs the unified root harness directly.

## Coding Style & Naming Conventions

Use 4-space indentation, `snake_case` functions and modules, and type hints where they clarify benchmark contracts. In CVRP, keep domain models in `domain/models.py`, validation in `domain/utils.py`, and solver adapters in `solver/<name>.py`. In employee scheduling, keep loaders in `loader.py`, validation in `validation.py`, and solver adapters in `solver/<name>.py`. Adapter names should match CLI arguments such as `solverforge`, `pyvrp`, `timefold_java`, or `ortools`.

## Testing Guidelines

There is no dedicated pytest suite. Treat quick benchmark targets and validation scripts as smoke tests. For CVRP, run `make validate-cvrp` plus one quick benchmark target. For employee scheduling, run `make bench-employee-scheduling-quick`. When adding a dataset or solver, include a small deterministic run and confirm failures are solution failures, not loader or adapter errors.

## Commit & Pull Request Guidelines

This checkout does not include local Git history. Use concise Conventional Commit subjects, for example `docs: add contributor guide` or `fix: correct cvrp validation`, with a body when behavior or interpretation changes. Pull requests should describe the scenario, commands run, generated files, and solver/runtime assumptions. Avoid committing generated CSVs unless they are intentional evidence artifacts.

## Agent-Specific Instructions

Keep changes tightly scoped. For documentation-only requests, update documentation only; do not modify solver adapters, benchmark runner behavior, generated result handling, or build flow. For benchmark execution changes, preserve one shared framework: problem adapters may load data, create solvers, validate/evaluate solutions, and expose native fields, but must not own orchestration loops, timing policy, watchdog policy, or CSV policy. The nominal benchmark budget is not a hard kill deadline; preserve late returned solutions and record overshoot. Only the separate watchdog may terminate runaway processes.
