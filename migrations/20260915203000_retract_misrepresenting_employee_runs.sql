-- Retract employee-scheduling runs that misrepresent the benchmark.
--
-- Two classes of employee-scheduling runs cannot stand as claims about
-- the pinned adapters and are removed at run granularity so each
-- remaining run keeps an intact exact-matrix attestation:
--
-- 1. Runs measured by superseded adapter versions (native solverforge
--    <= 0.19.3, solverforge-py <= 0.6.5). Those releases carried adapter
--    defects -- most visibly the solverforge-py 0.6.5 wave that returned
--    hard-infeasible schedules at nearly every budget -- fixed by the
--    pinned 0.19.4 and 0.6.6 releases.
--
-- 2. Runs containing OR-Tools employee-scheduling results produced
--    before the CP-SAT default-search fix (commit d9b3b4a, filed
--    2026-09-15T19:57:43+02:00). The adapter then pinned CP-SAT to
--    FIXED_SEARCH with a greedy TRUE-first decision strategy and a
--    single worker, so the recorded rows understate OR-Tools at every
--    budget (no incumbent at 1s/10s, roughly 2x cost at 60s) while the
--    binary reports the same OR-Tools version string as the fixed one.
--    Runtime-provenance hashes differ, but the version skew is not
--    visible in solver_version, so the affected runs are retracted by
--    date instead.
--
-- Foreign keys cascade the deletion to the runs' result rows, matrix
-- entries, and solver-version attestations. No-op on fresh warehouses
-- and on any warehouse that has only post-retraction runs.

DELETE FROM benchmark_runs
WHERE id IN (
    SELECT DISTINCT results.run_id
    FROM benchmark_results AS results
    JOIN benchmark_solver_versions AS versions
      ON versions.id = results.solver_version_id
    WHERE results.benchmark_name = 'employee-scheduling'
      AND versions.solver IN ('solverforge', 'solverforge-py')
      AND versions.solver_version IN (
          '0.17.1', '0.17.2', '0.18.0', '0.19.0', '0.19.3',
          '0.5.0', '0.6.1', '0.6.2', '0.6.5'
      )
)
OR id IN (
    SELECT DISTINCT results.run_id
    FROM benchmark_results AS results
    WHERE results.benchmark_name = 'employee-scheduling'
      AND results.solver = 'ortools'
      AND results.created_at < '2026-09-15T19:57:43+02:00'
);
