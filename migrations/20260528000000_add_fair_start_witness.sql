DROP VIEW latest_benchmark_result_facts;
DROP VIEW latest_benchmark_runs;
DROP VIEW benchmark_result_facts;

ALTER TABLE benchmark_results
    ADD COLUMN fair_start_valid boolean NOT NULL DEFAULT false,
    ADD COLUMN fair_start_error text,
    ADD COLUMN fair_start_witness jsonb NOT NULL DEFAULT 'null'::jsonb;

UPDATE benchmark_results
SET fair_start_error = 'legacy row lacks fair-start witness'
WHERE fair_start_error IS NULL;

ALTER TABLE benchmark_results
    ADD CONSTRAINT benchmark_results_fair_start_invalid_has_reason
        CHECK (fair_start_valid OR fair_start_error IS NOT NULL);

CREATE INDEX benchmark_results_fair_start_valid_idx
    ON benchmark_results (fair_start_valid);

CREATE INDEX benchmark_results_fair_start_witness_idx
    ON benchmark_results USING gin (fair_start_witness);

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
    results.fair_start_valid,
    results.fair_start_error,
    results.fair_start_witness,
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
