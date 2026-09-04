-- The full pinned catalog is versioned beside the JSSP data. These are the
-- entries whose official values differ from legacy rows emitted before the
-- catalog was introduced; unchanged legacy values are read from native_fields.
CREATE TABLE benchmark_reference_overrides (
    benchmark_name text NOT NULL,
    dataset text NOT NULL,
    instance text NOT NULL,
    reference_cost double precision NOT NULL CHECK (reference_cost > 0),
    lower_bound double precision NOT NULL CHECK (lower_bound > 0),
    upper_bound double precision NOT NULL CHECK (upper_bound > 0),
    reference_kind text NOT NULL CHECK (reference_kind IN ('known_optimum', 'best_known_upper_bound')),
    source_name text NOT NULL,
    source_revision text NOT NULL,
    PRIMARY KEY (benchmark_name, dataset, instance)
);

INSERT INTO benchmark_reference_overrides (
    benchmark_name, dataset, instance, reference_cost, lower_bound,
    upper_bound, reference_kind, source_name, source_revision
) VALUES
    ('job-shop-scheduling', 'JSPLIB', 'abz8', 667, 667, 667, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'abz9', 678, 678, 678, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv03', 1398, 1398, 1398, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv04', 1464, 1464, 1464, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv06', 1667, 1667, 1667, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv07', 1594, 1541, 1594, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv08', 1751, 1694, 1751, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv09', 1655, 1655, 1655, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv10', 1743, 1692, 1743, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv11', 2983, 2983, 2983, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv12', 2972, 2972, 2972, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'swv15', 2885, 2885, 2885, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'yn1', 884, 884, 884, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'yn2', 904, 904, 904, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'yn3', 892, 892, 892, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'yn4', 967, 967, 967, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta11', 1357, 1357, 1357, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta12', 1367, 1367, 1367, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta13', 1342, 1342, 1342, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta15', 1339, 1339, 1339, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta16', 1360, 1360, 1360, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta18', 1396, 1396, 1396, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta19', 1332, 1332, 1332, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta20', 1348, 1348, 1348, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta21', 1642, 1642, 1642, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta22', 1600, 1600, 1600, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta23', 1557, 1557, 1557, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta24', 1644, 1644, 1644, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta25', 1595, 1595, 1595, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta26', 1643, 1643, 1643, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta27', 1680, 1680, 1680, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta28', 1603, 1603, 1603, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta29', 1625, 1625, 1625, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta30', 1584, 1562, 1584, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta32', 1783, 1774, 1783, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta33', 1791, 1791, 1791, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta34', 1828, 1828, 1828, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta37', 1771, 1771, 1771, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta40', 1669, 1658, 1669, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta41', 2005, 1926, 2005, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta42', 1937, 1900, 1937, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta43', 1846, 1809, 1846, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta44', 1978, 1961, 1978, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta45', 1997, 1997, 1997, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta46', 2002, 1976, 2002, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta47', 1889, 1827, 1889, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta48', 1937, 1921, 1937, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta49', 1960, 1938, 1960, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta50', 1923, 1848, 1923, 'best_known_upper_bound', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta71', 5464, 5464, 5464, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta72', 5181, 5181, 5181, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta73', 5568, 5568, 5568, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta74', 5339, 5339, 5339, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta75', 5392, 5392, 5392, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta76', 5342, 5342, 5342, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta77', 5436, 5436, 5436, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta78', 5394, 5394, 5394, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta79', 5358, 5358, 5358, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399'),
    ('job-shop-scheduling', 'JSPLIB', 'ta80', 5183, 5183, 5183, 'known_optimum', 'ScheduleOpt/benchmarks', '2f0500c4d4c1a5588778004dc47954240e65d399');

CREATE OR REPLACE VIEW benchmark_result_facts AS
WITH enriched AS (
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
        results.quality_ratio,
        results.validation_error,
        results.solution_artifact,
        results.native_fields,
        results.row_payload,
        overrides.reference_cost AS override_reference_cost,
        CASE
            WHEN overrides.reference_cost IS NOT NULL THEN overrides.reference_cost
            WHEN results.benchmark_name = 'job-shop-scheduling' THEN COALESCE(
                NULLIF(results.native_fields ->> 'upper_bound_makespan', '')::double precision,
                NULLIF(results.native_fields ->> 'known_best_makespan', '')::double precision,
                results.reference_cost
            )
            ELSE results.reference_cost
        END AS effective_reference_cost
    FROM benchmark_runs AS runs
    JOIN benchmark_results AS results ON results.run_id = runs.id
    JOIN benchmark_solver_versions AS versions ON versions.id = results.solver_version_id
    LEFT JOIN benchmark_reference_overrides AS overrides
        ON overrides.benchmark_name = results.benchmark_name
       AND overrides.dataset = results.dataset
       AND overrides.instance = results.instance
)
SELECT
    run_id,
    run_kind,
    nightly,
    release_tag,
    run_stamp,
    run_status,
    result_count,
    git_commit,
    git_dirty,
    run_created_at,
    run_completed_at,
    log_path,
    row_index,
    benchmark_name,
    benchmark_category,
    dataset,
    dataset_set,
    instance,
    instance_size,
    solver,
    solver_version_id,
    solver_version,
    solver_version_source,
    solver_version_metadata,
    time_limit_seconds,
    actual_time_seconds,
    overshoot_seconds,
    overshoot_ratio,
    wall_time_over_limit,
    watchdog_limit_seconds,
    watchdog_killed,
    fair_start_valid,
    fair_start_error,
    fair_start_witness,
    run_error,
    solver_stdout_path,
    solver_stderr_path,
    hard_feasible,
    cost,
    reported_cost,
    fresh_cost,
    effective_reference_cost AS reference_cost,
    CASE
        WHEN effective_reference_cost IS NOT NULL
             AND benchmark_name = 'job-shop-scheduling' THEN
            CASE
                WHEN hard_feasible IS TRUE AND cost IS NOT NULL
                THEN cost / effective_reference_cost
                ELSE NULL
            END
        ELSE quality_ratio
    END AS quality_ratio,
    validation_error,
    solution_artifact,
    native_fields,
    row_payload
FROM enriched;
