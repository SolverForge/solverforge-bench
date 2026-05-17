# Job-Shop Scheduling benchmark (JSSP)

## Why this benchmark exists

Current benchmark surface in this branch:

- CVRP (list-variable routing)
- INRC2 nurse rostering (scalar-variable assignment/scheduling)
- JSPLIB job-shop scheduling (scalar-variable machine scheduling)

The JSSP benchmark adds a third core optimization class while preserving the
same shared harness shape already used in this repository: deterministic
dataset loader, solver adapters, shared run matrix, shared timing/watchdog
policy, shared CSV/PostgreSQL logging, and shared result rows.

## Dataset selection

Use the public benchmark ecosystem around JSPLIB / OR-Library classic JSSP
instances.

Primary sources:

- JSPLIB benchmark catalog: <https://scheduleopt.github.io/benchmarks/jsplib/>
- OR-Library job-shop instances: <https://people.brunel.ac.uk/~mastjjb/jeb/orlib/jobshopinfo.html>

Bundled instances in this branch:

- `ft06` from the FT family, known best makespan `55`
- `la01` from the LA family, known best makespan `666`
- `la02` from the LA family, known best makespan `655`

The manifest currently defines:

- `quick`: `ft06`, `la01`
- `canonical`: `ft06`, `la01`, `la02`

## Repository layout

The problem package follows the existing benchmark pattern:

- `scalar-variable/job-shop-scheduling/`
  - `src/job_shop_bench/__init__.py`
  - `src/job_shop_bench/spec.py`
  - `src/job_shop_bench/loader.py`
  - `src/job_shop_bench/domain/models.py`
  - `src/job_shop_bench/validation.py`
  - `src/job_shop_bench/solver/instance_json.py`
  - `src/job_shop_bench/solver/solver.py` (adapter registry)
  - `src/job_shop_bench/solver/solverforge.py`
  - `src/job_shop_bench/solver/solverforge_jssp/`
  - `src/job_shop_bench/solver/ortools/`
  - `src/job_shop_bench/solver/timefold.py`
  - `src/job_shop_bench/solver/timefold/`
  - `data/jsplib/...` (instance files + manifest)
  - `scripts/validate_all.py`

The benchmark framework remains centralized in `src/solverforge_bench/`.

## Data model and objective

Use a canonical JSSP definition:

- Jobs: ordered operation chains
- Each operation: `(machine_id, duration)`
- Hard constraints:
  - Precedence within each job
  - No overlap for operations sharing a machine
- Objective: minimize makespan

Current instance model:

```python
@dataclass(frozen=True)
class Operation:
    job_id: int
    op_index: int
    machine_id: int
    duration: int

@dataclass(frozen=True)
class JobShopInstance:
    name: str
    family: str
    num_jobs: int
    num_machines: int
    operations_by_job: tuple[tuple[Operation, ...], ...]
```

## Solver output contract

Standardize solver return payload so validation is strict and comparable:

- Per-operation start times for every operation.
- `reported_makespan`, which is compared against a fresh Python validator value.
- No missing operation and no unassigned start may be fabricated into a valid
  schedule.

A validated schedule must produce:

- `hard_feasible = True/False`
- `cost` = validator-computed makespan when feasible
- `reported_cost` = solver-reported makespan when present
- `validation_error` when infeasible/invalid

## Solver adapters

Registered job-shop scheduling solvers are:

- `solverforge`: Rust/PyO3 SolverForge model in `solver/solverforge_jssp/`.
  It uses scalar operation start-time variables, hard constraints for assigned
  starts, job precedence, and machine non-overlap, and a soft objective that
  minimizes makespan.
- `timefold`: Java Timefold model in `solver/timefold/`, packaged as
  `timefold-jssp.jar`.
- `ortools`: native C++ OR-Tools CP-SAT model in `solver/ortools/`.

The deterministic dispatch schedule is only used inside SolverForge and
Timefold as an initial seed. It is not a registered benchmark solver.

## Native result fields

The benchmark exposes native columns similar to existing adapters:

- `num_jobs`
- `num_machines`
- `num_operations`
- `source_family` (for example `ft` or `la` in the current manifest)
- `known_best_makespan` (if available in manifest)
- `makespan_gap_to_best` (if known best present)

These are produced by the job-shop benchmark spec and passed to the shared
framework row writer.

## Manifests and run groups

`data/jsplib/manifest.json` owns deterministic groups and known-best metadata.
The current manifest intentionally stays small for this PR: two quick smoke
instances and three canonical instances.

## CLI and config integration

The root harness integration does not change shared policy:

- Benchmark id: `job-shop-scheduling`
- Benchmark-specific selector options in the adapter layer only:
  - `--dataset-set`
  - `--datasets`

Update `benchmark.example.toml`:

```toml
benchmark = "job-shop-scheduling"

[benchmarks.job-shop-scheduling]
dataset_set = "quick"
datasets = ["ft06"]
```

## Make targets

Root targets mirror existing conventions:

- `make validate-job-shop-scheduling`
- `make build-job-shop-scheduling`
- `make build-job-shop-scheduling-solverforge`
- `make build-job-shop-scheduling-timefold`
- `make build-job-shop-scheduling-ortools`
- `make bench-job-shop-scheduling-quick`
- `make bench-job-shop-scheduling-quick-db`
- `make bench-job-shop-scheduling`
- `make bench-job-shop-scheduling-db`

## Validation logic

`validation.py` verifies:

1. Every operation appears exactly once.
2. Start times are non-negative.
3. Job precedence respected.
4. Machine disjunctive constraints respected.
5. Makespan computed from operation end times.

Return deterministic error messages so solver failures are distinguishable from loader/adapter bugs.

## Smoke-test commands

- `make validate-job-shop-scheduling`
- `make bench-job-shop-scheduling-quick`
- `PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src .venv/bin/python3 scripts/run_benchmark.py job-shop-scheduling --run-kind quick --dataset-set quick --solver solverforge --time-limits 1`
- `PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src .venv/bin/python3 scripts/run_benchmark.py job-shop-scheduling --run-kind quick --dataset-set quick --time-limits 1 10`

## Risks and mitigations

- **Instance format variance**: keep loader format-specific and normalize to one in-memory model.
- **Objective comparability**: make makespan the only scored objective for now.
- **Solver-output shape differences**: adapt all solver outputs into one canonical schedule payload before validation.

## Current status

JSSP is implemented as the third benchmark family in this branch. It is
problem-class specific, publicly benchmarked, scalable from quick to nightly,
and fits the same shared harness architecture already used by this repository.
