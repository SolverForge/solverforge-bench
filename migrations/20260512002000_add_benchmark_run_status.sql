CREATE TYPE benchmark_run_status AS ENUM ('running', 'completed', 'failed');

ALTER TABLE benchmark_runs
    ADD COLUMN status benchmark_run_status NOT NULL DEFAULT 'running',
    ADD COLUMN completed_at timestamptz,
    ADD COLUMN failure_error text,
    ADD COLUMN result_count integer NOT NULL DEFAULT 0;

CREATE INDEX benchmark_runs_status_created_at_idx
    ON benchmark_runs (status, created_at DESC);

DROP VIEW latest_benchmark_result_facts;
DROP VIEW latest_benchmark_runs;
DROP VIEW benchmark_result_facts;

CREATE VIEW benchmark_result_facts AS
SELECT
    runs.id AS run_id,
    runs.run_kind,
    runs.release_tag,
    runs.run_stamp,
    runs.status AS run_status,
    runs.result_count,
    runs.git_commit,
    runs.git_dirty,
    runs.created_at AS run_created_at,
    runs.completed_at AS run_completed_at,
    results.row_index,
    results.benchmark_name,
    results.benchmark_category,
    results.dataset,
    results.dataset_set,
    results.instance,
    results.instance_size,
    results.solver,
    results.time_limit_seconds,
    results.actual_time_seconds,
    results.overshoot_seconds,
    results.overshoot_ratio,
    results.wall_time_over_limit,
    results.watchdog_limit_seconds,
    results.watchdog_killed,
    results.run_error,
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
JOIN benchmark_results AS results ON results.run_id = runs.id;

CREATE VIEW latest_benchmark_runs AS
SELECT DISTINCT ON (run_kind, benchmark_name, release_tag)
    id,
    run_kind,
    release_tag,
    run_stamp,
    status,
    completed_at,
    result_count,
    benchmark_name,
    benchmark_category,
    output_path,
    artifact_dir,
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
ORDER BY run_kind, benchmark_name, release_tag, completed_at DESC, id DESC;

CREATE VIEW latest_benchmark_result_facts AS
SELECT facts.*
FROM benchmark_result_facts AS facts
JOIN latest_benchmark_runs AS latest ON latest.id = facts.run_id;
