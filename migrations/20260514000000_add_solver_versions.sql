DROP VIEW latest_benchmark_result_facts;
DROP VIEW latest_benchmark_runs;
DROP VIEW benchmark_result_facts;

CREATE TABLE benchmark_solver_versions (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    solver text NOT NULL,
    solver_version text NOT NULL,
    version_source text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, run_id, solver),
    UNIQUE (run_id, solver)
);

ALTER TABLE benchmark_results
    ADD COLUMN solver_version_id bigint;

INSERT INTO benchmark_solver_versions (
    run_id,
    solver,
    solver_version,
    version_source
)
SELECT
    run_id,
    solver,
    'unknown',
    'legacy_migration'
FROM benchmark_results
GROUP BY run_id, solver;

UPDATE benchmark_results AS results
SET solver_version_id = versions.id
FROM benchmark_solver_versions AS versions
WHERE versions.run_id = results.run_id
  AND versions.solver = results.solver;

ALTER TABLE benchmark_results
    ALTER COLUMN solver_version_id SET NOT NULL,
    ADD CONSTRAINT benchmark_results_solver_version_fk
        FOREIGN KEY (solver_version_id, run_id, solver)
        REFERENCES benchmark_solver_versions(id, run_id, solver);

CREATE INDEX benchmark_solver_versions_run_idx
    ON benchmark_solver_versions (run_id, solver);

CREATE INDEX benchmark_results_solver_version_idx
    ON benchmark_results (solver_version_id);

CREATE VIEW benchmark_result_facts AS
SELECT
    runs.id AS run_id,
    runs.run_kind,
    runs.nightly,
    runs.release_tag,
    runs.run_stamp,
    runs.status AS run_status,
    runs.result_count,
    runs.git_commit,
    runs.git_dirty,
    runs.created_at AS run_created_at,
    runs.completed_at AS run_completed_at,
    runs.log_path,
    results.row_index,
    results.benchmark_name,
    results.benchmark_category,
    results.dataset,
    results.dataset_set,
    results.instance,
    results.instance_size,
    results.solver,
    results.solver_version_id,
    versions.solver_version,
    versions.version_source AS solver_version_source,
    versions.metadata AS solver_version_metadata,
    results.time_limit_seconds,
    results.actual_time_seconds,
    results.overshoot_seconds,
    results.overshoot_ratio,
    results.wall_time_over_limit,
    results.watchdog_limit_seconds,
    results.watchdog_killed,
    results.run_error,
    results.solver_stdout_path,
    results.solver_stderr_path,
    results.hard_feasible,
    results.cost,
    results.reported_cost,
    results.fresh_cost,
    results.reference_cost,
    results.quality_ratio,
    results.validation_error,
    results.solution_artifact,
    results.native_fields,
    results.row_payload
FROM benchmark_runs AS runs
JOIN benchmark_results AS results ON results.run_id = runs.id
JOIN benchmark_solver_versions AS versions ON versions.id = results.solver_version_id;

CREATE VIEW latest_benchmark_runs AS
SELECT DISTINCT ON (nightly, run_kind, benchmark_name, release_tag)
    id,
    run_kind,
    nightly,
    release_tag,
    run_stamp,
    status,
    completed_at,
    result_count,
    benchmark_name,
    benchmark_category,
    output_path,
    artifact_dir,
    log_path,
    solvers,
    time_limits_seconds,
    command_args,
    repo_root,
    git_commit,
    git_dirty,
    python_version,
    metadata,
    created_at
FROM benchmark_runs
WHERE status = 'completed'
ORDER BY nightly, run_kind, benchmark_name, release_tag, completed_at DESC, id DESC;

CREATE VIEW latest_benchmark_result_facts AS
SELECT facts.*
FROM benchmark_result_facts AS facts
JOIN latest_benchmark_runs AS latest ON latest.id = facts.run_id;
