# Proposal: Add a Job-Shop Scheduling benchmark (JSSP)

## Why this fills the benchmark gap

Current benchmark surface:

- CVRP (list-variable routing)
- INRC2 nurse rostering (scalar-variable assignment/scheduling)

Missing surface:

- Machine scheduling with precedence + disjunctive machine capacity.

A JSSP benchmark adds a third core optimization class while preserving the same shared harness shape already used in this repository: deterministic dataset loader, solver adapters, shared run matrix, shared timing/watchdog policy, shared CSV/postgres logging.

## Dataset selection

Use the public benchmark ecosystem around JSPLIB / OR-Library classic JSSP instances.

Primary sources:

- JSPLIB benchmark catalog: <https://scheduleopt.github.io/benchmarks/jsplib/>
- OR-Library job-shop instances: <https://people.brunel.ac.uk/~mastjjb/jeb/orlib/jobshopinfo.html>

Suggested bundled families:

- Small/medium classics for quick runs: FT, LA, ORB, ABZ, YN
- Larger stress set for candidate/nightly: TA (Taillard)

## Repository layout

Add a new problem package following the existing pattern:

- `scalar-variable/job-shop-scheduling/`
  - `src/job_shop_bench/__init__.py`
  - `src/job_shop_bench/spec.py`
  - `src/job_shop_bench/loader.py`
  - `src/job_shop_bench/domain/models.py`
  - `src/job_shop_bench/validation.py`
  - `src/job_shop_bench/solver/solver.py` (adapter protocol)
  - `src/job_shop_bench/solver/solverforge.py`
  - `src/job_shop_bench/solver/ortools.py` (optional parity baseline)
  - `data/jsplib/...` (instance files + manifest)
  - `scripts/validate_all.py`
  - `Makefile`

The benchmark framework remains centralized in `src/solverforge_bench/`.

## Data model and objective

Use a canonical JSSP definition:

- Jobs: ordered operation chains
- Each operation: `(machine_id, duration)`
- Hard constraints:
  - Precedence within each job
  - No overlap for operations sharing a machine
- Objective: minimize makespan

Recommended instance model:

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
    num_jobs: int
    num_machines: int
    operations_by_job: tuple[tuple[Operation, ...], ...]
    source_family: str
```

## Solver output contract

Standardize solver return payload so validation is strict and comparable:

- Per-operation start times (or equivalent machine sequences convertible to starts)
- Optional solver-native metadata (`best_bound`, `search_nodes`, `status_text`)

A validated schedule must produce:

- `feasible = True/False`
- `objective_value` = makespan when feasible
- `violation` string when infeasible/invalid

## Native result fields

Add benchmark-native columns similar to existing adapters:

- `num_jobs`
- `num_machines`
- `num_operations`
- `source_family` (ft/la/orb/abz/yn/ta)
- `known_best_makespan` (if available in manifest)
- `makespan_gap_to_best` (if known best present)

These should be produced by the adapter and passed to the shared framework row writer.

## Manifests and run groups

Create `data/jsplib/manifest.json` with deterministic groups:

- `quick`: ~6 instances across multiple families (fast smoke)
- `canonical`: balanced medium set
- `stress`: larger TA-heavy set

Example quick candidates:

- `ft06`, `ft10`, `la16`, `orb04`, `abz6`, `ta20`

## CLI and config integration

Integrate with root harness without changing shared policy:

- Add benchmark id: `job-shop-scheduling`
- Add benchmark-specific selector options in the adapter layer only:
  - `--dataset-set`
  - `--datasets`

Update `benchmark.example.toml`:

```toml
benchmark = "job-shop-scheduling"

[benchmarks.job-shop-scheduling]
dataset_set = "quick"
datasets = ["ft06", "la16"]
```

## Make targets

Add root targets mirroring existing conventions:

- `make validate-job-shop-scheduling`
- `make bench-job-shop-scheduling-quick`
- `make bench-job-shop-scheduling`
- `make bench-job-shop-scheduling-quick-db`

## Validation logic

`validation.py` should verify:

1. Every operation appears exactly once.
2. Start times are non-negative.
3. Job precedence respected.
4. Machine disjunctive constraints respected.
5. Makespan computed from operation end times.

Return deterministic error messages so solver failures are distinguishable from loader/adapter bugs.

## Implementation phases

1. **Phase 1: skeleton + parser + validator**
   - Loader for selected JSPLIB format
   - Strict validation + makespan evaluation
   - One solver adapter (SolverForge)
2. **Phase 2: harness registration + TOML/CLI plumbing**
   - Add benchmark spec to registry
   - Add quick/canonical groups and make targets
3. **Phase 3: baseline parity + reporting polish**
   - Optional OR-Tools baseline adapter
   - Known-best manifest enrichment
   - Gap metrics in summaries

## Smoke-test commands

- `make validate-job-shop-scheduling`
- `make bench-job-shop-scheduling-quick`
- `PYTHONPATH=src:list-variable/cvrp/src:scalar-variable/employee-scheduling/src:scalar-variable/job-shop-scheduling/src .venv/bin/python3 scripts/run_benchmark.py job-shop-scheduling --run-kind quick --datasets ft06 la16 --time-limits 1 10`

## Risks and mitigations

- **Instance format variance**: keep loader format-specific and normalize to one in-memory model.
- **Objective comparability**: make makespan the only scored objective for now.
- **Solver-output shape differences**: adapt all solver outputs into one canonical schedule payload before validation.

## Recommendation

Proceed with JSSP as the third benchmark family. It is problem-class specific, publicly benchmarked, scalable from quick to nightly, and fits the same shared harness architecture already used by this repository.
