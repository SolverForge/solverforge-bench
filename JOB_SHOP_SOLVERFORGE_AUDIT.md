# Job-Shop Scheduling Benchmark Audit

Date: 2026-05-23

Run ID: `c6815384-80b2-4339-b32b-e5819a8c9595`

CSV: `scalar-variable/job-shop-scheduling/data/benchmark_job_shop_scheduling_20260523_100602_724853.csv`

Log: `logs/job-shop-scheduling_20260523_100602_724853/job-shop-scheduling_20260523_100602_724853.log`

## Executive Finding

The previous "full" job-shop run was short because the benchmark manifest's
`canonical` group only covered three instances. The harness was not truncating
the run. The current dataset is the full classic JSPLIB corpus from
`tamy0612/JSPLIB`: 162 instances across `abz`, `ft`, `la`, `orb`, `swv`, `ta`,
and `yn`.

The completed full run wrote all expected rows:

```text
162 instances * 3 solvers * 3 time limits = 1458 rows
```

SolverForge is losing because the current JSSP adapter models each operation's
absolute start time as an independent scalar variable over `0..horizon`, seeds
every operation with a greedy dispatch start, and then relies on default scalar
change/swap local search. That search shape cannot perform the coordinated
machine-sequence reorderings and left-shifts that JSSP needs.

This is not a parser, dataset, timing, database, watchdog, or feasibility
problem. SolverForge returned feasible solutions on all 486 SolverForge rows.
The quality problem is that those solutions are almost always exactly the
initial dispatch schedule.

## Canonical Dataset

Current local proof:

```text
local .txt files: 162
manifest instances: 162
manifest groups.canonical: 162
manifest groups.quick: 2
manifest unknown optimum count: 59
families: abz, ft, la, orb, swv, ta, yn
```

The live upstream metadata at
`https://raw.githubusercontent.com/tamy0612/JSPLIB/master/instances.json` was
checked during the audit and contained 162 unique names in the same seven
families. The local manifest's `instances` list and `groups.canonical` list are
identical.

The old completed DB run `ee679f39-4df3-4ed0-acec-bfa1e019540e` had 27 rows:

```text
3 instances * 3 solvers * 3 time limits = 27 rows
```

That explains the short benchmark. It was the old canonical group, not the
shared runner.

## Completed Full Run

The clean run was started after aborting a contaminated attempt that was sharing
CPU 0 with CVRP and employee-scheduling runs. The completed run used:

```text
benchmark: job-shop-scheduling
run_kind: candidate
dataset_set: canonical
solvers: solverforge, timefold, ortools
time_limits: 1, 10, 60 seconds
created_at: 2026-05-23 10:06:02.836118+02
completed_at: 2026-05-23 19:04:22.334331+02
elapsed: 08:58:19.498213
status: completed
result_count: 1458
```

Health:

| Solver | Rows | Feasible | Infeasible | Watchdog kills | Process errors |
|---|---:|---:|---:|---:|---:|
| OR-Tools | 486 | 486 | 0 | 0 | 0 |
| SolverForge | 486 | 486 | 0 | 0 | 0 |
| Timefold | 486 | 485 | 1 | 0 | 0 |

The single invalid row was Timefold on `orb07` at 60 seconds:

```text
Machine overlap on 0: (8, 9) and (9, 9)
```

## Solver Ranking

Known optimum/best instances: 103 instances. Gap is `(cost - known_best) /
known_best`; `0.0830` means 8.30%.

| Time limit | Solver | Known rows | Avg gap | Median gap | Max gap |
|---:|---|---:|---:|---:|---:|
| 1s | OR-Tools | 103 | 0.0830 | 0.0680 | 0.2677 |
| 1s | Timefold | 103 | 5.8179 | 5.7063 | 13.8342 |
| 1s | SolverForge | 103 | 5.9141 | 5.7389 | 13.8342 |
| 10s | OR-Tools | 103 | 0.0564 | 0.0196 | 0.2583 |
| 10s | Timefold | 103 | 4.3562 | 3.8256 | 13.7916 |
| 10s | SolverForge | 103 | 5.9141 | 5.7389 | 13.8342 |
| 60s | OR-Tools | 103 | 0.0377 | 0.0000 | 0.2036 |
| 60s | Timefold | 102 | 2.8557 | 1.1766 | 12.9593 |
| 60s | SolverForge | 103 | 5.8996 | 5.7389 | 13.8342 |

Overall known-best ranking:

| Solver | Known rows | Avg gap | Median gap |
|---|---:|---:|---:|
| OR-Tools | 309 | 0.0591 | 0.0222 |
| Timefold | 308 | 4.3481 | 3.0963 |
| SolverForge | 309 | 5.9092 | 5.7389 |

Best-feasible wins/ties by instance and time limit:

| Solver | Rows | Wins or ties | Avg rank |
|---|---:|---:|---:|
| OR-Tools | 486 | 486 | 1.000 |
| Timefold | 485 | 1 | 1.998 |
| SolverForge | 486 | 0 | 2.722 |

Unknown-optimum instances with lower bounds available: 49 instances. Gap is
relative to the lower bound.

| Time limit | Solver | Rows | Avg gap to LB | Median gap to LB |
|---:|---|---:|---:|---:|
| 1s | OR-Tools | 49 | 0.2470 | 0.2437 |
| 1s | Timefold | 49 | 8.5015 | 9.2548 |
| 1s | SolverForge | 49 | 8.5015 | 9.2548 |
| 10s | OR-Tools | 49 | 0.1738 | 0.1663 |
| 10s | Timefold | 49 | 7.7197 | 8.5173 |
| 10s | SolverForge | 49 | 8.5015 | 9.2548 |
| 60s | OR-Tools | 49 | 0.1334 | 0.1328 |
| 60s | Timefold | 49 | 4.8322 | 4.9428 |
| 60s | SolverForge | 49 | 8.5015 | 9.2548 |

## Why SolverForge Is Losing

### 1. The adapter preassigns the entire solution

`scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/solverforge_jssp/src/lib.rs`
computes a greedy dispatch schedule and assigns every operation's start before
the SolverForge solve begins:

```text
dispatch_starts: lines 49-63
build_plan: lines 65-93
JsspOperation.start = Some(starts[id]): line 83
start_values = 0..=horizon: line 88
```

`domain.rs` declares `start` as the planning variable:

```text
#[planning_variable(value_range_provider = "start_values", allows_unassigned = true)]
pub start: Option<usize>
```

Because every `start` is already `Some`, construction has no scalar work to do.
This is confirmed by SolverForge core behavior:

```text
../solverforge/crates/solverforge-solver/src/descriptor/bindings/lookup.rs lines 76-113
../solverforge/crates/solverforge-solver/src/descriptor/construction/placer.rs lines 290-298
```

Both skip scalar variables that already have a value.

### 2. The model has the right hard constraints but the wrong search shape

The SolverForge constraints match job-shop feasibility and makespan scoring:

```text
assignedStart
jobPrecedence
machineNoOverlap
makespan
```

They are in
`scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/solverforge_jssp/src/constraints.rs`
lines 8-51.

The issue is the neighborhood. The solver configuration is just:

```toml
[[phases]]
type = "construction_heuristic"
construction_heuristic_type = "first_fit"
entity_class = "JsspOperation"
variable_name = "start"

[[phases]]
type = "local_search"
```

With this scalar-only model, SolverForge defaults to scalar change/swap moves:

```text
default scalar change/swap: ../solverforge/.../defaults.rs lines 35-50
scalar selector append: ../solverforge/.../defaults.rs lines 182-194
scalar-only acceptor: ../solverforge/.../defaults.rs lines 225-254
scalar-only forager limit: ../solverforge/.../defaults.rs lines 257-276
AcceptedCountForager(1): ../solverforge/.../phase/localsearch/forager.rs lines 63-68
```

That means local search explores one absolute start-time change or one start
swap at a time over very large domains. It is not doing machine-sequence moves,
block moves, critical-path moves, or a coordinated repair/left-shift move.

### 3. Dispatch comparison proves SolverForge barely moves

Comparing each returned cost to the greedy dispatch makespan:

| Solver | Time | Rows | Same as dispatch | Improved | Worse |
|---|---:|---:|---:|---:|---:|
| SolverForge | 1s | 162 | 162 | 0 | 0 |
| SolverForge | 10s | 162 | 162 | 0 | 0 |
| SolverForge | 60s | 162 | 161 | 1 | 0 |
| Timefold | 1s | 162 | 118 | 44 | 0 |
| Timefold | 10s | 162 | 15 | 147 | 0 |
| Timefold | 60s | 161 | 1 | 160 | 0 |
| OR-Tools | 1s | 162 | 0 | 162 | 0 |
| OR-Tools | 10s | 162 | 0 | 162 | 0 |
| OR-Tools | 60s | 162 | 0 | 162 | 0 |

SolverForge's only improvement over dispatch was `ft06` at 60 seconds:

```text
dispatch makespan: 152
SolverForge 60s cost: 70
known best: 55
```

Every other SolverForge row was exactly the greedy dispatch schedule.

### 4. The immediate neighborhood has no improving move

A direct neighborhood probe from the dispatch solution found zero improving
feasible one-start or start-swap neighbors on representative instances:

| Instance | Ops | Horizon | Dispatch | Known best | One-start improving | Start-swap improving |
|---|---:|---:|---:|---:|---:|---:|
| ft06 | 36 | 197 | 152 | 55 | 0 / 7,092 | 0 / 626 |
| la01 | 50 | 2,849 | 2,272 | 666 | 0 / 142,450 | 0 / 1,216 |
| abz5 | 100 | 7,773 | 6,446 | 1,234 | 0 / 777,300 | 0 / 4,938 |
| abz6 | 100 | 5,946 | 4,526 | 943 | 0 / 594,600 | 0 / 4,936 |

This is the exact local-search failure mode: a good JSSP move usually changes
relative machine order and then left-shifts several operations. A single scalar
start edit usually either violates precedence/no-overlap or does not reduce the
makespan. A start swap is similarly ineffective because the values are absolute
times, not sequence positions.

### 5. Timefold and OR-Tools confirm the diagnosis

Timefold is intentionally comparable: its adapter also creates a scalar
start-time model and dispatch initialization:

```text
scalar start range and dispatch starts:
scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/timefold/src/main/java/com/solverforgebench/jssp/Main.java lines 79-98

solver config:
lines 99-106
```

Timefold still improves much more than SolverForge, so the issue is not the
loader or the basic feasibility constraints. It is SolverForge's current
default scalar search behavior on this model.

OR-Tools uses a CP-SAT interval model with `NoOverlap` and makespan minimization:

```text
interval variables: scalar-variable/job-shop-scheduling/src/job_shop_bench/solver/ortools/main.cc lines 92-118
job precedence: lines 120-128
machine no-overlap: lines 131-133
makespan objective: lines 135-138
```

That is the right representation for this benchmark. It exposes the disjunctive
scheduling structure directly, which is why OR-Tools dominates this run.

## Scale of the Search Space

Canonical JSPLIB instance scale:

```text
operations min/median/max: 36 / 300 / 2000
horizon min/median/max: 197 / 15078.5 / 101716
scalar change candidates min/median/max: 7,128 / 4,624,200 / 203,434,000
start swap candidates min/median/max: 630 / 44,850 / 1,999,000
```

Largest scalar-change cases:

```text
ta77 ops=2000 horizon=101716 scalar_change=203434000 swap=1999000
ta71 ops=2000 horizon=100891 scalar_change=201784000 swap=1999000
ta73 ops=2000 horizon=100622 scalar_change=201246000 swap=1999000
ta76 ops=2000 horizon=100371 scalar_change=200744000 swap=1999000
ta74 ops=2000 horizon=100049 scalar_change=200100000 swap=1999000
```

This makes the scalar absolute-time representation a poor benchmark for
SolverForge's current defaults.

## Verification Commands

Completed successfully:

```bash
make validate-job-shop-scheduling
make bench-job-shop-scheduling-db BENCH_ARGS="--no-show-solver-output --no-capture-solver-output"
make normalize-results INPUT=scalar-variable/job-shop-scheduling/data/benchmark_job_shop_scheduling_20260523_100602_724853.csv OUTPUT=/tmp/jobshop-full-normalized.csv
.venv/bin/python3 -m compileall -q src list-variable/cvrp/src scalar-variable/employee-scheduling/src scalar-variable/job-shop-scheduling/src scripts
.venv/bin/python3 - <<'PY'
import tomllib
from pathlib import Path
for name in ['benchmark.example.toml','benchmark.nightly.example.toml']:
    tomllib.loads(Path(name).read_text())
PY
```

Validation output:

```text
validated 162 instances
```

Normalization output:

```text
/tmp/jobshop-full-normalized.csv has 1459 lines
1458 data rows + header
```

## Conclusion

The canonical dataset and full run are now real. SolverForge is losing with
absolute clarity because this adapter asks it to solve JSSP through independent
absolute start-time scalar moves from a fully assigned greedy dispatch schedule.
The default scalar neighborhood almost never escapes that dispatch solution.

The next real fix is not another benchmark-run tweak. It is a modeling/search
change: represent machine sequencing directly, or add an upstream SolverForge
move/repair family that can reorder machine blocks and left-shift affected
operations as a coordinated move.
