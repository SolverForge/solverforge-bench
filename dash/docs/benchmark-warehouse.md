# Benchmark Warehouse

The dashboard reads the SolverForge benchmark PostgreSQL warehouse through
Active Record read-only models.

## Connection

Development defaults to:

```sh
postgresql://postgres@localhost/solverforge_bench
```

Set `BENCH_DATABASE_URL` for any other host. Production requires
`BENCH_DATABASE_URL`.

## Tables

`benchmark_runs` is the run catalog. It records the run kind (`quick`,
`candidate`, `tag`), nightly flag, release tag, benchmark name/category, solver
set, time limits, repo metadata, status (`running`, `completed`, `failed`),
completion time, result count, and run log path.

`benchmark_solver_versions` records one solver-version row per solver in a run.
Versions are discovered from the native executable or package metadata rather
than Makefile defaults.

`benchmark_results` stores one row per solver, instance, and time limit. Core
metrics are typed columns: feasibility, cost variants, quality ratio, runtime,
overshoot, watchdog state, error text, and solver log paths. Benchmark-specific
native fields stay in `native_fields`; the full emitted payload stays in
`row_payload`.

## Views

Display code should prefer the warehouse views instead of hand-rebuilding joins:

- `benchmark_result_facts`: completed and partial result facts joined to run and
  solver-version metadata.
- `latest_benchmark_runs`: latest completed run per `(nightly, run_kind,
  benchmark_name, release_tag)`.
- `latest_benchmark_result_facts`: result facts for the latest completed runs.

The dashboard uses `latest_benchmark_result_facts` for current slices and
`benchmark_result_facts` for over-time charts.
